import asyncio
import pandas as pd
import requests
import json
import os
import re
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- CẤU HÌNH ---
OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"
AI_MODEL = "qwen2.5:7b" 
REPORT_FILENAME = "qwen2.5.xlsx"

CATEGORIES_LIST = [
    "Access Control", "Arithmetic", "Bad Randomness", "Denial of Service",
    "Front Running", "Reentrancy", "Short Addresses", "Time Manipulation",
    "Unchecked Low Level Calls"
]

def add_line_numbers(code):
    """Thêm số dòng để Qwen định vị chính xác lỗi."""
    lines = code.split('\n')
    return '\n'.join([f"{i+1}: {line}" for i, line in enumerate(lines)])

def request_ai_audit(source_code):
    numbered_code = add_line_numbers(source_code)

    prompt = f"""
    Role: Senior Smart Contract Auditor.
    Task: Analyze the provided Solidity code. Identify the SINGLE most severe vulnerability from this list:
    {', '.join(CATEGORIES_LIST)}

    [CRITICAL RULE - REENTRANCY EXCLUSION]:
    - Solidity's 'transfer()' and 'send()' functions have a fixed gas stipend of 2300 gas.
    - This gas limit makes reentrancy attacks MATHEMATICALLY IMPOSSIBLE.
    - If the contract uses 'transfer()' or 'send()', you are STRICTLY FORBIDDEN from labeling it as 'Reentrancy', even if the balance update happens after the call.
    - Only 'call.value()()' is susceptible to Reentrancy.

    [CRITICAL RULE - UNCHECKED CALLS]:
    - If a 'call()' or 'send()' is wrapped inside an 'if' statement (e.g., `if(x.call())`) or a 'require()', it is considered CHECKED.
    - DO NOT label such cases as 'Unchecked Low Level Calls'.
       
    Instructions:
    1. Select ONLY ONE category.
    2. Reference the LINE NUMBERS provided in the Numbered Code.
    3. Respond ONLY in JSON format.

    Required JSON Structure:
    {{
      "vulnerability": "name",
      "line": "number",
      "reasoning": "think step by step detailed technical explanation"
    }}

    Numbered Code to analyze:
    {numbered_code}
    """
    
    payload = {
        "model": AI_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.2, 
            "num_predict": 1500, 
            "num_ctx": 32768   
        }
    }
    
    try:
        response = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=300)
        raw_output = response.json().get("response", "").strip()

        try:
            start_idx = raw_output.find('{')
            end_idx = raw_output.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean_json_str = raw_output[start_idx:end_idx+1]
                data = json.loads(clean_json_str, strict=False)
            else:
                data = json.loads(raw_output, strict=False)

            return {
                "vulnerability": data.get("vulnerability", "Clean"),
                "line": data.get("line", "N/A"),
                "reasoning": data.get("reasoning", "No technical details.")
            }
        except:
            vul_match = re.search(r'"vulnerability"\s*:\s*"(.*?)"', raw_output)
            reason_match = re.search(r'"reasoning"\s*:\s*"(.*?)"', raw_output)
            return {
                "vulnerability": vul_match.group(1) if vul_match else "Parse Error",
                "line": "Check Raw",
                "reasoning": reason_match.group(1) if reason_match else raw_output
            }

    except Exception as e:
        return {"vulnerability": "Request Failed", "line": "N/A", "reasoning": str(e)}

async def start_audit():
    server_params = StdioServerParameters(command="python", args=["mcp_server.py"])
    final_data = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            list_tool = await session.call_tool("list_contracts", arguments={})
            files = [f.strip() for f in list_tool.content[0].text.split(",") if f.strip()]

            print(f"🚀 Qwen 3 Coder starting audit for {len(files)} files...")

            for index, rel_path in enumerate(files, start=1):
                category_label = os.path.dirname(rel_path)
                filename = os.path.basename(rel_path)
                
                print(f"[{index}/{len(files)}] 🔍 Auditing: {filename}")
                
                content_tool = await session.call_tool("read_contract", arguments={"file_relative_path": rel_path})
                source_code = content_tool.content[0].text

                ai_result = request_ai_audit(source_code)

                row = {
                    "STT": index,
                    "Name": filename,
                    "Label vul": category_label.replace("_", " ").title(),
                    "LLM vul": ai_result["vulnerability"],
                    "Label line": "Check Dataset",
                    "LLM line": ai_result["line"],
                    "Reasoning": ai_result["reasoning"]
                }
                final_data.append(row)
                
                pd.DataFrame(final_data).to_excel(REPORT_FILENAME, index=False)

    print(f"✅ Complete! Báo cáo đã sẵn sàng: {REPORT_FILENAME}")

if __name__ == "__main__":
    asyncio.run(start_audit())