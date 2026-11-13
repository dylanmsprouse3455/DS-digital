"""Mocked, no-mail, no-external-network publication verification tests."""
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from verified_notification import NotificationOutbox, DeliveryBlocker, read_public_article

URL="https://dsdigitaldesigns.org/greeneville/proposed-test-article.html"
RID="0123456789abcdef0123456789abcdef"
HTML=('<html><head><link rel="canonical" href="'+URL+'"></head>'
      '<body><h1>Verified fictional test</h1></body></html>').encode("utf-8")
CONTENT_HASH=sha256(HTML).hexdigest()


class FakeResponse:
    def __init__(self,body=HTML,status=200,url=URL,content_type="text/html"):
        self.data=body
        self.status=status
        self.url=url
        self.headers=Message()
        self.headers["Content-Type"]=content_type
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def geturl(self):return self.url
    def read(self,length):return self.data[:length]


def fake_fetch(request,timeout=15):
    if request.full_url!=URL or timeout!=15:
        raise RuntimeError("unexpected simulated request")
    return FakeResponse()


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="ds-mail-outbox-")
        self.addCleanup(self.tmp.cleanup)
        self.outbox=NotificationOutbox(Path(self.tmp.name)/"private")
        self.assertEqual(self.outbox.status(),[])

    def queue(self,rid=RID):
        return self.outbox.verify_and_queue(
            rid,URL,CONTENT_HASH,"Proposed Synthetic Town Example",fetch=fake_fetch
        )

    def test_verified_public_page_can_queue_once(self):
        item=self.queue()
        self.assertTrue(item["public_page_verified"])
        self.assertEqual(item["status"],"verified")
        self.assertEqual(self.outbox.status()[0]["status"],"verified")

    def test_replay_does_not_duplicate(self):
        self.assertTrue(self.queue()["new"])
        self.assertFalse(self.queue()["new"])
        self.assertEqual(len(self.outbox.status()),1)

    def test_wrong_content_hash_prevents_queue(self):
        with self.assertRaisesRegex(DeliveryBlocker,"bytes differ"):
            self.outbox.verify_and_queue(RID,URL,"0"*64,"Synthetic Test",fetch=fake_fetch)
        self.assertEqual(self.outbox.status(),[])

    def test_non_200_does_not_queue(self):
        with self.assertRaisesRegex(DeliveryBlocker,"HTTP 200"):
            read_public_article(URL,CONTENT_HASH,fetch=lambda *_a,**_kw:FakeResponse(status=404))

    def test_redirect_to_different_url_prevents_queue(self):
        with self.assertRaisesRegex(DeliveryBlocker,"redirected"):
            read_public_article(URL,CONTENT_HASH,fetch=lambda *_a,**_kw:FakeResponse(url=URL+"?cache=1"))

    def test_bad_content_type_prevents_queue(self):
        with self.assertRaisesRegex(DeliveryBlocker,"not HTML"):
            read_public_article(URL,CONTENT_HASH,
                fetch=lambda *_a,**_kw:FakeResponse(content_type="application/octet-stream"))

    def test_no_canonical_prevents_queue(self):
        body=b"<html>this is not the expected article</html>"
        with self.assertRaisesRegex(DeliveryBlocker,"canonical"):
            read_public_article(URL,sha256(body).hexdigest(),fetch=lambda *_a,**_kw:FakeResponse(body=body))

    def test_only_public_https_domain_is_eligible(self):
        for url in ["http://dsdigitaldesigns.org/greeneville/proposed-test-article.html",
                    "http://127.0.0.1/greeneville/proposed-test-article.html",
                    "https://evil.example/greeneville/proposed-test-article.html",
                    "https://dsdigitaldesigns.org/greeneville/proposed-test-article.html?ref=a",
                    "https://dsdigitaldesigns.org/index.html"]:
            with self.subTest(url=url):
                with self.assertRaises(DeliveryBlocker):
                    read_public_article(url,CONTENT_HASH,fetch=fake_fetch)

    def test_incomplete_article_hash_rejected(self):
        with self.assertRaisesRegex(DeliveryBlocker,"SHA-256"):
            read_public_article(URL,"bad",fetch=fake_fetch)

    def test_email_eligible_only_after_verification(self):
        with self.assertRaisesRegex(DeliveryBlocker,"not available"):
            self.outbox.claim(RID)
        self.queue()
        claimed=self.outbox.claim(RID)
        self.assertIn(URL,claimed["body"])
        self.assertEqual(claimed["delivery_status"],"SENDING_NOT_YET_SENT")
        self.assertEqual(self.outbox.status()[0]["status"],"sending")

    def test_concurrent_claim_only_one_succeeds(self):
        self.queue()
        def claim(_):
            try:
                self.outbox.claim(RID)
                return True
            except DeliveryBlocker:
                return False
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(claim,range(6)))
        self.assertEqual(results.count(True),1)
        self.assertEqual(results.count(False),5)

    def test_after_claim_no_duplicate_automatic_retry(self):
        self.queue()
        self.outbox.claim(RID)
        with self.assertRaisesRegex(DeliveryBlocker,"already claimed"):
            self.outbox.claim(RID)

    def test_uncertain_send_blocks_retry(self):
        self.queue()
        self.outbox.claim(RID)
        self.outbox.mark_uncertain(RID,"Gmail timeout: may have been delivered")
        self.assertEqual(self.outbox.status()[0]["status"],"uncertain")
        with self.assertRaisesRegex(DeliveryBlocker,"already claimed"):
            self.outbox.claim(RID)
        self.assertFalse(self.outbox.status()[0]["gmail_id_present"])

    def test_ack_requires_gmail_message_id(self):
        self.queue()
        self.outbox.claim(RID)
        with self.assertRaisesRegex(DeliveryBlocker,"message ID"):
            self.outbox.record_sent(RID,"")
        self.assertEqual(self.outbox.status()[0]["status"],"sending")

    def test_mock_connector_receipt_marks_simulated_sent_only(self):
        # Fictional receipt: no Gmail API was called; this test checks state transition.
        self.queue()
        self.outbox.claim(RID)
        self.outbox.record_sent(RID,"MOCK_NOT_REAL_GMAIL_01234567")
        result=self.outbox.status()[0]
        self.assertEqual(result["status"],"sent")
        self.assertTrue(result["gmail_id_present"])
        with self.assertRaises(DeliveryBlocker):
            self.outbox.claim(RID)

    def test_record_sent_before_claim_is_rejected(self):
        self.queue()
        with self.assertRaisesRegex(DeliveryBlocker,"active send"):
            self.outbox.record_sent(RID,"MOCK_RECEIPT_123456789")

    def test_different_release_same_id_blocked(self):
        self.queue()
        revised=HTML.replace(b"Verified fictional test",b"Second fictional article")
        with self.assertRaisesRegex(DeliveryBlocker,"different published receipt"):
            self.outbox.verify_and_queue(RID,URL,sha256(revised).hexdigest(),
                                          "Proposed Synthetic Test",fetch=lambda *_a,**_kw:FakeResponse(body=revised))

    def test_db_permissions_are_owner_only(self):
        self.assertEqual(self.outbox.path.stat().st_mode&0o777,0o600)
        self.assertEqual(self.outbox.root.stat().st_mode&0o777,0o700)


if __name__=="__main__":
    unittest.main(verbosity=2)