(function(){

const WORKER_URL = "https://dsdigital.your-subdomain.workers.dev"; // ← replace

// ===== CREATE HTML =====
const widget = document.createElement("div");
widget.innerHTML = `
<style>
#ds-chat-btn{
  position:fixed;
  bottom:20px;
  right:20px;
  width:60px;
  height:60px;
  border-radius:50%;
  background:#2563eb;
  color:white;
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:26px;
  cursor:pointer;
  box-shadow:0 8px 20px rgba(0,0,0,.2);
  z-index:9999;
}

#ds-chat-box{
  position:fixed;
  bottom:90px;
  right:20px;
  width:320px;
  height:420px;
  background:white;
  border-radius:14px;
  box-shadow:0 10px 30px rgba(0,0,0,.2);
  display:none;
  flex-direction:column;
  overflow:hidden;
  z-index:9999;
  font-family:system-ui;
}

#ds-chat-header{
  background:#2563eb;
  color:white;
  padding:12px;
  font-weight:600;
}

#ds-chat-messages{
  flex:1;
  padding:12px;
  overflow-y:auto;
  font-size:14px;
}

.ds-msg-user{margin:6px 0;text-align:right}
.ds-msg-bot{margin:6px 0;text-align:left;color:#333}

#ds-chat-input{
  display:flex;
  border-top:1px solid #e5e7eb;
}

#ds-chat-input input{
  flex:1;
  border:none;
  padding:12px;
  font-size:14px;
  outline:none;
}

#ds-chat-input button{
  background:#2563eb;
  color:white;
  border:none;
  padding:12px 16px;
  cursor:pointer;
}
</style>

<div id="ds-chat-btn">💬</div>

<div id="ds-chat-box">
  <div id="ds-chat-header">DSDigital</div>
  <div id="ds-chat-messages"></div>
  <div id="ds-chat-input">
    <input id="ds-input" placeholder="Ask something..." />
    <button id="ds-send">Send</button>
  </div>
</div>
`;

document.body.appendChild(widget);

// ===== ELEMENTS =====
const btn = document.getElementById("ds-chat-btn");
const box = document.getElementById("ds-chat-box");
const messages = document.getElementById("ds-chat-messages");
const input = document.getElementById("ds-input");
const send = document.getElementById("ds-send");

// ===== TOGGLE =====
btn.onclick = () => {
  box.style.display = box.style.display==="flex"?"none":"flex";
  box.style.display="flex";
};

// ===== MESSAGE ADDER =====
function addMsg(text,cls){
  const div=document.createElement("div");
  div.className=cls;
  div.textContent=text;
  messages.appendChild(div);
  messages.scrollTop=messages.scrollHeight;
}

// ===== SEND =====
async function sendMsg(){
  const text=input.value.trim();
  if(!text) return;

  addMsg(text,"ds-msg-user");
  input.value="";

  addMsg("Thinking...","ds-msg-bot");

  try{
    const res = await fetch(WORKER_URL,{
      method:"POST",
      body:text
    });

    const data = await res.json();
    messages.lastChild.remove();

    addMsg(data.response || "No reply","ds-msg-bot");

  }catch(e){
    messages.lastChild.remove();
    addMsg("Error talking to AI","ds-msg-bot");
  }
}

send.onclick = sendMsg;
input.addEventListener("keypress",e=>{
  if(e.key==="Enter") sendMsg();
});

})();