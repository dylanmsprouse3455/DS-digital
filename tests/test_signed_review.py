"""Synthetic Ed25519 reviewer approvals: no real production key or signing service."""
from __future__ import annotations
import base64
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
from signed_review import (
    approval_message, canonical_bytes, verify_signature, ApprovalBlocked,
    secure_preflight
)
from production_quota import ProductionLedger
from test_publication_gate import PolicyTests
from test_release_coordinator import T0


class SignedReviewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="ds-editor-signed-test-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.private_key=Ed25519PrivateKey.generate()  # never exported or persisted
        pub=self.private_key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        self.pub=self.root/"pinned-editor-public.b64"
        self.pub.write_text(base64.b64encode(pub).decode())
        self.pub.chmod(0o600)
        self.att=self.root/"approval.json"
        self.story_id="fictional-town-agenda"
        self.hash="a"*64
        self.editor="ds-editor-trusted-task"
        self.writer="ds-writer-other-task"
        self.write_approval()

    def write_approval(self, **changes):
        issued=changes.pop("issued_at",T0.isoformat())
        expires=changes.pop("expires_at",(T0+timedelta(hours=3)).isoformat())
        msg=approval_message(self.story_id,self.hash,self.editor,
                             issued_at=issued,expires_at=expires)
        msg.update(changes)
        signature=self.private_key.sign(canonical_bytes(msg))
        self.att.write_text(json.dumps({
            "key_id":"ds-editor-v1","message":msg,
            "signature_b64":base64.b64encode(signature).decode()
        }))
        self.att.chmod(0o600)

    def verify(self,**kwargs):
        return verify_signature(self.att,self.pub,
            kwargs.get("story_id",self.story_id),
            kwargs.get("payload_sha",self.hash),
            kwargs.get("reviewer_id",self.editor),
            kwargs.get("writer_id",self.writer),
            kwargs.get("at",T0+timedelta(minutes=5)))

    def test_exact_approved_story_is_verified(self):
        proof=self.verify()
        self.assertTrue(proof["verified"])
        self.assertFalse(proof["owner_activation"])
        self.assertEqual(proof["payload_sha256"],self.hash)

    def test_changed_payload_rejected(self):
        with self.assertRaisesRegex(ApprovalBlocked,"does not match"):
            self.verify(payload_sha="b"*64)

    def test_other_story_rejected(self):
        with self.assertRaisesRegex(ApprovalBlocked,"does not match"):
            self.verify(story_id="different-story")

    def test_forged_reviewer_rejected(self):
        with self.assertRaisesRegex(ApprovalBlocked,"does not match"):
            self.verify(reviewer_id="forged-editor")

    def test_writer_cannot_be_editor(self):
        with self.assertRaisesRegex(ApprovalBlocked,"identities must differ"):
            self.verify(writer_id=self.editor)

    def test_expired_review_rejected(self):
        with self.assertRaisesRegex(ApprovalBlocked,"expired"):
            self.verify(at=T0+timedelta(hours=4))

    def test_future_review_rejected(self):
        self.write_approval(issued_at=(T0+timedelta(hours=1)).isoformat(),
                            expires_at=(T0+timedelta(hours=2)).isoformat())
        with self.assertRaisesRegex(ApprovalBlocked,"time-invalid"):
            self.verify()

    def test_long_lived_approval_rejected(self):
        self.write_approval(expires_at=(T0+timedelta(days=30)).isoformat())
        with self.assertRaisesRegex(ApprovalBlocked,"bounded validity"):
            self.verify()

    def test_modified_signature_rejected(self):
        doc=json.loads(self.att.read_text())
        doc["message"]["repository"]="another-owner/DS-digital"
        self.att.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ApprovalBlocked,"does not match"):
            self.verify()

    def test_other_pubkey_rejected(self):
        k=Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        self.pub.write_text(base64.b64encode(k).decode())
        with self.assertRaisesRegex(ApprovalBlocked,"signature not verified"):
            self.verify()

    def test_key_identifier_allowlist_enforced(self):
        doc=json.loads(self.att.read_text())
        doc["key_id"]="rogue-editor-key"
        self.att.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ApprovalBlocked,"unrecognized"):
            self.verify()

    def test_group_writable_trust_file_rejected(self):
        self.pub.chmod(0o664)
        with self.assertRaisesRegex(ApprovalBlocked,"writable"):
            self.verify()

    def test_symlink_public_key_rejected(self):
        link=self.root/"linked-public-key.b64"
        link.symlink_to(self.pub)
        with self.assertRaisesRegex(ApprovalBlocked,"symlink"):
            verify_signature(self.att,link,self.story_id,self.hash,
                             self.editor,self.writer,T0)

    def test_missing_signature_rejected(self):
        self.att.unlink()
        with self.assertRaisesRegex(ApprovalBlocked,"unavailable"):
            self.verify()

    def test_unknown_extra_field_rejected(self):
        doc=json.loads(self.att.read_text())
        doc["unexpected_action"]="publish_now"
        self.att.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ApprovalBlocked,"unknown"):
            self.verify()

    def test_approval_cannot_grant_deployment(self):
        self.assertFalse(self.verify()["owner_activation"])
        self.assertFalse("send_gmail" in self.verify())

class SignedIntegrationTests(PolicyTests):
    """Reuse actual synthetic source/production-ledger fixtures."""
    def setUp(self):
        super().setUp()
        self.private_key=Ed25519PrivateKey.generate()
        pub=self.private_key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        self.pub=self.root/"pinned-review-key.b64"
        self.pub.write_text(base64.b64encode(pub).decode())
        self.pub.chmod(0o600)
        self.att=self.root/"signed-review.json"
        self.write_editor_approval()

    def write_editor_approval(self):
        from release_coordinator import digest
        payload_sha=digest(self.story)
        msg=approval_message(self.story["id"],payload_sha,"independent-editor",
              issued_at=T0.isoformat(),expires_at=(T0+timedelta(hours=4)).isoformat())
        self.att.write_text(json.dumps({
            "key_id":"ds-editor-v1","message":msg,
            "signature_b64":base64.b64encode(self.private_key.sign(canonical_bytes(msg))).decode()
        }))
        self.att.chmod(0o600)

    def test_signed_gate_succeeds_and_does_not_deploy(self):
        r=secure_preflight(
            self.story["id"],ledger=self.ledger,main=self.main,remote_sha=self.sha,
            editorial_db=self.store.path,source_db=self.collector,
            attestation_file=self.att,public_key_file=self.pub,at=T0+timedelta(minutes=5))
        self.assertTrue(r["signed_editor_review"]["verified"])
        self.assertFalse(r["publication_enabled"])
        self.assertEqual(self.ledger.inspect(T0)["remaining_slots"],4)

    def test_unsigned_gate_fails_closed(self):
        self.att.unlink()
        with self.assertRaises(ApprovalBlocked):
            secure_preflight(self.story["id"],ledger=self.ledger,main=self.main,
                 remote_sha=self.sha,editorial_db=self.store.path,
                 source_db=self.collector,attestation_file=self.att,
                 public_key_file=self.pub,at=T0)

if __name__=="__main__":
    unittest.main(verbosity=2)