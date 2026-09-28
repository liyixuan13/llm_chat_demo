import requests
import os
from dotenv import load_dotenv

# 【重点】先加载.env文件
load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")
api_url = os.getenv("DEEPSEEK_API_URL")

# 密钥校验（注意：永远不要把密钥打印出来或写进代码）
if not api_key:
    print("错误：没有读取到 DEEPSEEK_API_KEY！请检查 .env 文件位置和内容")
    exit()
if not api_url:
    print("错误：没有读取到 DEEPSEEK_API_URL！请检查 .env 文件")
    exit()

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
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7
    }
    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        ai_reply = result["choices"][0]["message"]["content"]
        print(f"AI：{ai_reply}")
        messages.append({"role":"assistant", "content": ai_reply})
    except requests.exceptions.RequestException as e:
        print(f"请求出错：{e}")
        messages.pop()
