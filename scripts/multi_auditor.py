import asyncio
import pandas as pd
import requests
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- CẤU HÌNH ---
OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"
AI_MODEL = "qwen3-coder:30b" 
REPORT_FILENAME = "qwen3-coder_final_report.xlsx"

CATEGORIES_LIST = [
    "Access Control", "Arithmetic", "Bad Randomness", "Denial of Service",
    "Front Running", "Reentrancy", "Short Addresses", "Time Manipulation",
    "Unchecked Low Level Calls"
]

def add_line_numbers(code):
    """Thêm số dòng để AI định vị chính xác lỗi."""
    lines = code.split('\n')
    return '\n'.join([f"{i+1}: {line}" for i, line in enumerate(lines)])

def request_ai_audit(source_code):
    numbered_code = add_line_numbers(source_code)

    prompt = f"""
    [ROLE]: Senior Smart Contract Auditor.
    [TASK]: Audit the code and identify ONLY valid vulnerabilities from: {', '.join(CATEGORIES_LIST)}.
    
    [STRICT AUDIT RULES]:
    1. CHECKED VS UNCHECKED: 
       - Every low-level call (`call`, `send`, `delegatecall`) MUST have its return value checked (e.g., using `require(success)`, `if(success)`, or `bool success = ...`).
       - If the return value is ignored (e.g., `target.call(...)` without checking the result), it is ALWAYS "Unchecked Low Level Calls".
    
    2. GAS LIMIT RULE: `transfer()` and `send()` are NEVER "Reentrancy" due to the 2300 gas limit. However, `send()` can still be "Unchecked Low Level Calls" if its return value is not checked.
    
    3. REENTRANCY LOGIC: 
       - If `call()` has an IF-CHECK but follows a "State Change after External Call" pattern, label as 'Reentrancy'.
       - If `call()` or `send()` has NO check for its return value, label as 'Unchecked Low Level Calls'.
    
    4. TIME MANIPULATION vs BLOCK NUMBER: 
       - ONLY report 'Time Manipulation' if `block.timestamp` is used for critical logic or randomness. 
       - DO NOT report `block.number` as 'Time Manipulation'. It is a sequential index (+1 per block) and cannot be arbitrarily manipulated by miners.
    
    5. RANDOMNESS: Use of `block.timestamp`, `blockhash`, or `now` for lottery/random seed = 'Bad Randomness'.

    6. ARITHMETIC CHECK: 
       - Before reporting Over/Underflow, double-check for existing `if` or `require` guards.
       - Example: `if(Holders[_addr] >= _wei) {{ Holders[_addr] -= _wei; }}` is NOT a vulnerability.
       - DO NOT report arithmetic operations that are already protected by logical checks.

    [NEGATIVE CONSTRAINT]:
    - If a potential finding violates any of the [STRICT AUDIT RULES] above, it is NOT a vulnerability. 
    - DO NOT include it in the JSON "findings" list. 
    - If no valid vulnerabilities are found, return: {{"findings": []}}

    [CONSTRAINTS]:
    - Respond ONLY in JSON format.
    - Each "reasoning" MUST be exactly or less than 5 sentences.
    - Be technical, precise, and do not provide prose outside JSON.

    [OUTPUT FORMAT]:
    {{
      "findings": [
        {{
          "vulnerability": "name",
          "line": "number",
          "reasoning": "detailed technical explanation of why this is a valid vulnerability, referencing specific code patterns and the audit rules."
        }}
      ]
    }}

    Numbered Code:
    {numbered_code}
    """
    
    payload = {
        "model": AI_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
            "num_predict": 2048,
            "num_ctx": 32768
        }
    }
    
    try:
        response = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=300)
        raw_output = response.json().get("response", "").strip()
        
        start_idx = raw_output.find('{')
        end_idx = raw_output.rfind('}')
        if start_idx != -1 and end_idx != -1:
            data = json.loads(raw_output[start_idx:end_idx+1], strict=False)
            return data.get("findings", [])
        return []
    except Exception as e:
        print(f"Lỗi khi gọi AI: {e}")
        return []
    
async def start_audit():
    # Giả định file mcp_server.py nằm cùng thư mục
    server_params = StdioServerParameters(command="python", args=["mcp_server.py"])
    final_data = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Lấy danh sách file từ MCP Tool
            list_tool = await session.call_tool("list_contracts", arguments={})
            files = [f.strip() for f in list_tool.content[0].text.split(",") if f.strip()]

            print(f"🚀 Qwen 3 Coder starting audit for {len(files)} files...")

            for index, rel_path in enumerate(files, start=1):
                category_label = os.path.dirname(rel_path)
                filename = os.path.basename(rel_path)
                
                print(f"[{index}/{len(files)}] 🔍 Auditing: {filename}")
                
                # Đọc nội dung file từ MCP Tool
                content_tool = await session.call_tool("read_contract", arguments={"file_relative_path": rel_path})
                source_code = content_tool.content[0].text

                # Lấy kết quả Audit (là một list các findings)
                ai_findings = request_ai_audit(source_code)

                if ai_findings:
                    for finding in ai_findings:
                        row = {
                            "STT": index,
                            "Name": filename,
                            "Label vul": category_label.replace("_", " ").title(),
                            "LLM vul": finding.get("vulnerability", "Unknown"),
                            "Label line": "Check Dataset",
                            "LLM line": finding.get("line", "N/A"),
                            "Reasoning": finding.get("reasoning", "")
                        }
                        final_data.append(row)
                else:
                    # Trường hợp không tìm thấy lỗi
                    row = {
                        "STT": index,
                        "Name": filename,
                        "Label vul": category_label.replace("_", " ").title(),
                        "LLM vul": "Clean",
                        "Label line": "Check Dataset",
                        "LLM line": "-",
                        "Reasoning": "No vulnerabilities found following strict rules."
                    }
                    final_data.append(row)
                
                # Lưu file Excel liên tục để tránh mất dữ liệu
                pd.DataFrame(final_data).to_excel(REPORT_FILENAME, index=False)

    print(f"\n✅ Complete! Báo cáo đã sẵn sàng: {REPORT_FILENAME}")

if __name__ == "__main__":
    try:
        asyncio.run(start_audit())
    except KeyboardInterrupt:
        print("\nStopping...")