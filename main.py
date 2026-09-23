import requests
import os

# 加载.env里面的密钥

api_key = ("sk-3297d8ebb8674dc9b30cdae4a1de2202")
api_url = ("https://api.deepseek.com/chat/completions")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# 保存对话历史，实现多轮对话
messages = []
print("=== AI控制台对话，输入exit退出 ===")

while True:
    user_input = input("\n你：")
    if user_input.lower() == "exit":
        print("结束对话")
        break
    
    messages.append({"role":"user", "content":user_input})
    
    payload = {
        "model": "deepseek-chat", # 换成你选用的模型名
        "messages": messages,
        "temperature": 0.7
    }
    
    resp = requests.post(api_url, headers=headers, json=payload)
    result = resp.json()

    print(">>> 服务器返回的原始数据：", result)
    
    ai_reply = result["choices"][0]["message"]["content"]
    print(f"AI：{ai_reply}")
    messages.append({"role":"assistant", "content": ai_reply})
