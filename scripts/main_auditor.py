import asyncio
import requests
import json
import os
import re
import pandas as pd
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ── CẤU HÌNH ────────────────────────────────────────────────────────────────
OLLAMA_ENDPOINT  = "http://localhost:11434/api/generate"
AI_MODEL         = "qwen3-coder:30b"
CSV_PATH         = "sample_with_vulnerabilities.csv"
RESULTS_JSON     = "audit_results.json"   # lưu trung gian, crash-safe

# ── PARSE CSV → ground truth ─────────────────────────────────────────────────
def load_ground_truth(csv_path: str) -> dict:
    """
    Trả về dict: address (lowercase) → {order, vulnerability, lines}
    Xử lý cả 2 dạng tag:
      - "no"                                      → Clean
      - "529: time_manipulation; 563: time_manipulation"  → có lỗi + dòng
    """
    df = pd.read_csv(csv_path)
    ground_truth = {}

    for order, row in enumerate(df.itertuples(), start=1):
        address = str(row.contract).strip().lower()
        tag     = str(row.tag).strip()

        if tag == "no":
            ground_truth[address] = {
                "order":         order,
                "vulnerability": "Clean",
                "lines":         []
            }
        else:
            findings = []
            for part in tag.split(";"):
                part = part.strip()
                m = re.match(r"(\d+):\s*(\w+)", part)
                if m:
                    findings.append({
                        "line":          int(m.group(1)),
                        "vulnerability": m.group(2).replace("_", " ").title()
                    })

            ground_truth[address] = {
                "order":         order,
                # Lấy vulnerability xuất hiện nhiều nhất làm primary label
                "vulnerability": _most_common_vuln(findings),
                "lines":         [f["line"] for f in findings]
            }

    return ground_truth


def _most_common_vuln(findings: list) -> str:
    if not findings:
        return "Clean"
    counts = {}
    for f in findings:
        v = f["vulnerability"]
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=counts.get)


# ── NORMALIZE để so sánh TP/FP ───────────────────────────────────────────────
_ALIASES = {
    "unchecked low level calls": "unchecked low level calls",
    "unchecked low-level calls": "unchecked low level calls",
    "unchecked_low_level_calls": "unchecked low level calls",
    "unchecked low level call":  "unchecked low level calls",
    "reentrancy":                "reentrancy",
    "re-entrancy":               "reentrancy",
    "bad randomness":            "bad randomness",
    "time manipulation":         "time manipulation",
    "arithmetic":                "arithmetic",
    "access control":            "access control",
    "denial of service":         "denial of service",
    "dos":                       "denial of service",
    "front running":             "front running",
    "front-running":             "front running",
    "short addresses":           "short addresses",
    "short address":             "short addresses",
    "clean":                     "clean",
    "other":                     "other",
}

def normalize(vuln: str) -> str:
    return _ALIASES.get(vuln.lower().strip(), vuln.lower().strip())


# ── PROMPT & AI CALL ─────────────────────────────────────────────────────────
def add_line_numbers(code: str) -> str:
    lines = code.split('\n')
    return '\n'.join([f"{i+1}: {line}" for i, line in enumerate(lines)])


def request_ai_audit(source_code: str) -> dict:
    numbered_code = add_line_numbers(source_code)

    prompt = f"""
You are an expert smart contract security auditor. Your task is to identify the single most critical vulnerability in the Solidity contract below.
 
[VULNERABILITY CLASSES]:
Reentrancy | Unchecked Low Level Calls | Bad Randomness | Time Manipulation | Arithmetic | Access Control | Denial Of Service | Front Running | Short Addresses | Other
 
[HOW TO REASON]:
Read the contract as an attacker would. Ask yourself: what is the worst thing someone could do to this contract?
- Who controls the money or critical state? Can an unauthorized party access it?
- Is there any external call where the callee could take control back before this contract finishes?
- Can the outcome of a transaction be predicted or manipulated before it is mined?
- Are there any calculations that could silently overflow or underflow?
- Can one user force the contract into a state that blocks everyone else?
 
Focus on exploitability and real financial impact. A bug that lets an attacker drain funds is more critical than one that wastes gas.
 
[COMMON PITFALLS TO AVOID]:
- send() and transfer() use 2300 gas — they cannot trigger a reentrant call.
- block.number is not a timestamp — do not confuse it with time-based logic.
- An if() wrapping a call() means the return value IS being checked.
- Using block.timestamp to generate randomness is different from using it to enforce a deadline.
- A missing auth check on a sensitive function is a critical issue even if the function body looks simple.
[OUTPUT]: Respond ONLY in JSON. No text outside.
    {{
      "vulnerability": "<class name>",
      "line": "<line number>",
      "reasoning": "<max 3 sentences, cite specific line and pattern>"
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
            "temperature": 0.2, 
            "num_predict": 1500, 
            "num_ctx": 32768   
        }
    }

    try:
        response   = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=300)
        raw_output = response.json().get("response", "").strip()

        try:
            start = raw_output.find('{')
            end   = raw_output.rfind('}')
            data  = json.loads(raw_output[start:end+1], strict=False) \
                    if start != -1 and end != -1 \
                    else json.loads(raw_output, strict=False)

            return {
                "vulnerability": data.get("vulnerability", "Clean"),
                "line":          data.get("line", "N/A"),
                "reasoning":     data.get("reasoning", "No technical details.")
            }
        except Exception:
            vul_m    = re.search(r'"vulnerability"\s*:\s*"(.*?)"', raw_output)
            reason_m = re.search(r'"reasoning"\s*:\s*"(.*?)"', raw_output)
            return {
                "vulnerability": vul_m.group(1)    if vul_m    else "Parse Error",
                "line":          "Check Raw",
                "reasoning":     reason_m.group(1) if reason_m else raw_output
            }

    except Exception as e:
        return {"vulnerability": "Request Failed", "line": "N/A", "reasoning": str(e)}


# ── MAIN AUDIT ────────────────────────────────────────────────────────────────
async def start_audit():
    # 1. Load ground truth từ CSV
    ground_truth = load_ground_truth(CSV_PATH)
    csv_addresses = set(ground_truth.keys())
    print(f"📋 Loaded {len(ground_truth)} contracts từ CSV")

    # 2. Load kết quả cũ nếu đã chạy dở (resume mode)
    existing_results = {}
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, "r", encoding="utf-8") as f:
            for item in json.load(f):
                existing_results[item["address"]] = item
        print(f"♻️  Resume: đã có {len(existing_results)} kết quả, bỏ qua các file này")

    server_params = StdioServerParameters(command="python", args=["mcp_server.py"])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 3. Lấy toàn bộ .sol từ dataset (hỗ trợ cả 2 dạng cấu trúc thư mục)
            list_tool = await session.call_tool("list_contracts", arguments={})
            all_files = [f.strip() for f in list_tool.content[0].text.split(",") if f.strip()]

            # Build index: address → rel_path
            # Hỗ trợ: "category/0xABC.sol" và "0xABC.sol"
            dataset_index = {}
            for rel_path in all_files:
                filename = os.path.basename(rel_path)
                address  = filename.replace(".sol", "").lower()
                dataset_index[address] = rel_path

            # 4. Match CSV ↔ Dataset, theo đúng thứ tự CSV
            matched = []
            not_found = []
            for address, gt in sorted(ground_truth.items(), key=lambda x: x[1]["order"]):
                if address in dataset_index:
                    matched.append({
                        "address":  address,
                        "rel_path": dataset_index[address],
                        "gt":       gt
                    })
                else:
                    not_found.append(address)

            print(f"✅ Match: {len(matched)}/{len(ground_truth)} | ❌ Không tìm thấy: {len(not_found)}")
            if not_found:
                print(f"   Missing: {not_found[:5]}{'...' if len(not_found)>5 else ''}")

            print(f"\n{'='*80}")
            print(f" {AI_MODEL} — Auditing {len(matched)} contracts ".center(80, "="))
            print(f"{'='*80}\n")

            # 5. Audit từng file
            all_results = list(existing_results.values())

            for index, item in enumerate(matched, start=1):
                address = item["address"]

                # Bỏ qua nếu đã có kết quả (resume)
                if address in existing_results:
                    print(f"[{index}/{len(matched)}] ⏭️  Skip (done): {os.path.basename(item['rel_path'])}")
                    continue

                filename = os.path.basename(item["rel_path"])
                print(f"[{index}/{len(matched)}] 🔍 Auditing: {filename}")

                # Đọc source code qua MCP
                content_tool = await session.call_tool(
                    "read_contract",
                    arguments={"file_relative_path": item["rel_path"]}
                )
                source_code = content_tool.content[0].text

                # Gọi AI
                ai_result = request_ai_audit(source_code)

                # Lưu kết quả đầy đủ
                result = {
                    "order":          item["gt"]["order"],
                    "address":        address,
                    "filename":       filename,
                    "rel_path":       item["rel_path"],
                    "gt_vul":         item["gt"]["vulnerability"],
                    "gt_lines":       item["gt"]["lines"],
                    "llm_vul":        ai_result["vulnerability"],
                    "llm_line":       ai_result["line"],
                    "reasoning":      ai_result["reasoning"],
                }
                all_results.append(result)

                # Ghi JSON sau mỗi file — crash-safe
                with open(RESULTS_JSON, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Audit hoàn tất!")


if __name__ == "__main__":
    from report_builder import build_report

    try:
        asyncio.run(start_audit())
    except KeyboardInterrupt:
        print("\n⚠️  Bị ngắt bởi Ctrl+C — đang xuất kết quả hiện có...")
    finally:
        # Luôn xuất Excel dù chạy xong hay bị ngắt giữa chừng
        build_report()
