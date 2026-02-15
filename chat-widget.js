(function(){

// ===== YOUR WORKER URL =====
const WORKER_URL = "https://patient-tooth-ddfc.dylanm-sprouse3455.workers.dev";

// ===== WIDGET HTML + STYLE =====
const html = `
<style>

#ds-chat-btn{
 position:fixed;
 bottom:20px;
 right:20px;
 width:58px;
 height:58px;
 border-radius:50%;
 background:#2563eb;
 color:white;
 display:flex;
 align-items:center;
 justify-content:center;
 font-size:24px;
 cursor:pointer;
 box-shadow:0 6px 20px rgba(0,0,0,.25);
 z-index:9999;
}

#ds-chat-box{
 position:fixed;
 bottom:90px;
 right:20px;
 width:340px;
 height:460px;
 background:white;
 border-radius:16px;
 box-shadow:0 12px 30px rgba(0,0,0,.25);
 display:none;
 flex-direction:column;
 overflow:hidden;
 font-family:system-ui;
 z-index:9999;
}

#ds-chat-header{
 background:#2563eb;
 color:white;
 padding:14px;
 font-weight:600;
 font-size:15px;
}

#ds-chat-messages{
 flex:1;
 padding:14px;
 overflow-y:auto;
 background:#f9fafb;
}

.ds-msg{
 margin:8px 0;
 padding:10px 14px;
 border-radius:16px;
 max-width:80%;
 font-size:14px;
 line-height:1.4;
}

.ds-user{
 background:#2563eb;
 color:white;
 margin-left:auto;
 border-bottom-right-radius:4px;
}

.ds-bot{
 background:#e5e7eb;
 color:#111;
 border-bottom-left-radius:4px;
}

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
 padding:0 18px;
 cursor:pointer;
 font-size:16px;
}

</style>

<div id="ds-chat-btn">💬</div>

<div id="ds-chat-box">
 <div id="ds-chat-header">Chat with DSDigital</div>
 <div id="ds-chat-messages"></div>

 <div id="ds-chat-input">
  <input id="ds-input" placeholder="Ask about websites..." />
  <button id="ds-send">➤</button>
 </div>
</div>
`;

document.body.insertAdjacentHTML("beforeend", html);

// ===== ELEMENTS =====
const btn = document.getElementById("ds-chat-btn");
const box = document.getElementById("ds-chat-box");
const messages = document.getElementById("ds-chat-messages");
const input = document.getElementById("ds-input");
const send = document.getElementById("ds-send");

// ===== TOGGLE OPEN/CLOSE =====
btn.onclick = () => {
 box.style.display =
  box.style.display === "flex" ? "none" : "flex";
};

// ===== ADD MESSAGE =====
function addMessage(text, cls){
 const div = document.createElement("div");
 div.className = "ds-msg " + cls;
 div.textContent = text;
 messages.appendChild(div);
 messages.scrollTop = messages.scrollHeight;
}

// ===== SEND MESSAGE =====
async function sendMessage(){
 const text = input.value.trim();
 if(!text) return;

 addMessage(text, "ds-user");
 input.value = "";

 addMessage("Thinking...", "ds-bot");

 try{
  const res = await fetch(WORKER_URL,{
   method:"POST",
   body:text
  });

  const data = await res.json();
  messages.lastChild.remove();

  addMessage(data.response || "No reply", "ds-bot");

 }catch(err){
  messages.lastChild.remove();
  addMessage("Connection issue", "ds-bot");
 }
}

send.onclick = sendMessage;

input.addEventListener("keypress", e=>{
 if(e.key === "Enter") sendMessage();
});

})();