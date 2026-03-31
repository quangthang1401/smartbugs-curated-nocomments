import streamlit as st
import sqlite3
import pandas as pd
import json
import re
import os
from datetime import datetime

# Implemented clients
from openai import OpenAI
from anthropic import Anthropic
from google import genai

# Setup page config
st.set_page_config(page_title="Smart Contract Vuln Detector", layout="wide", page_icon="🕵️")

# Initialize database
DB_PATH = "data/history.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            model TEXT,
            timestamp DATETIME,
            result_json TEXT
        )
    ''')
    try:
        c.execute('ALTER TABLE scans ADD COLUMN prompt TEXT;')
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def save_scan(filename, model, result_json, prompt):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO scans (filename, model, timestamp, result_json, prompt) VALUES (?, ?, ?, ?, ?)',
              (filename, model, datetime.now(), str(result_json), prompt))
    conn.commit()
    conn.close()

def load_history():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query('SELECT filename, model, timestamp, result_json, prompt FROM scans ORDER BY timestamp DESC', conn)
    conn.close()
    return df

# Extractor for JSON
def extract_json(text):
    # Try to find JSON within code block
    match = re.search(r'```(?:json)?(.*?)```', text, re.DOTALL)
    if match:
        text = match.group(1)
    
    # Try parsing
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        # If it fails, try to find first { and last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end+1])
            except:
                pass
        return {"vulnerability": "Error", "line": "N/A", "reasoning": f"Failed to parse JSON. Raw output: {text}"}

# LLM call functions
def analyze_with_openai(prompt, code, api_key, model="gpt-5.4"):
    client = OpenAI(api_key=api_key)
    full_prompt = f"{prompt}\n\nCode to analyze:\n```\n{code}\n```"
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.1
    )
    return extract_json(response.choices[0].message.content)

def analyze_with_anthropic(prompt, code, api_key, model="claude-sonnet-4.6"):
    client = Anthropic(api_key=api_key)
    full_prompt = f"{prompt}\n\nCode to analyze:\n```\n{code}\n```"
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.1
    )
    return extract_json(response.content[0].text)

def analyze_with_gemini(prompt, code, api_key, model="gemini-3.1-pro"):
    client = genai.Client(api_key=api_key)
    full_prompt = f"{prompt}\n\nCode to analyze:\n```\n{code}\n```"
    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.1
        )
    )
    return extract_json(response.text)

# Main App
def main():
    init_db()
    
    # Sidebar
    st.sidebar.title("Configuration")
    
    openai_key = st.sidebar.text_input("OpenAI API Key", type="password")
    anthropic_key = st.sidebar.text_input("Anthropic API Key", type="password")
    gemini_key = st.sidebar.text_input("Gemini API Key", type="password")
    
    model_choice = st.sidebar.selectbox("Active Model", [
        "gpt-5.4", 
        "gpt-5.4-mini",
        "gpt-4o",
        "claude-opus-4.6",
        "claude-sonnet-4.6",
        "claude-3-5-sonnet-20241022",
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ])
    
    tab1, tab2 = st.tabs(["Analyze", "History"])
    
    with tab1:
        st.header("Smart Contract Analysis")
        
        default_prompt = (
            "You are an expert smart contract auditor. Analyze the following code for vulnerabilities.\\n"
            "Output ONLY a JSON object with the following exactly 3 fields:\\n"
            "- 'vulnerability': String (name of the bug, e.g., 'Reentrancy' or 'None').\\n"
            "- 'line': String (line number or range, e.g., '45-48', or 'N/A').\\n"
            "- 'reasoning': String (short explanation of the issue).\\n"
            "Do not output markdown block ticks, just the raw JSON object."
        )
        
        # Fixing the string literals so newlines display properly in the UI.
        default_prompt = default_prompt.replace("\\n", "\n")

        prompt_text = st.text_area("Chain-of-Thought Prompt", value=default_prompt, height=200)
        
        uploaded_files = st.file_uploader("Upload Code Files (.sol, .rs, etc.)", accept_multiple_files=True)
        
        if st.button("Start Analysis"):
            if not uploaded_files:
                st.warning("Please upload at least one file.")
                return
            
            # Check for API keys
            if "gpt" in model_choice and not openai_key:
                st.error("Please provide the OpenAI API Key.")
                return
            if "claude" in model_choice and not anthropic_key:
                st.error("Please provide the Anthropic API Key.")
                return
            if "gemini" in model_choice and not gemini_key:
                st.error("Please provide the Gemini API Key.")
                return
            
            for file in uploaded_files:
                code_content = file.getvalue().decode("utf-8", errors="ignore")
                with st.spinner(f"Analyzing {file.name} using {model_choice}..."):
                    try:
                        if "gpt" in model_choice:
                            result = analyze_with_openai(prompt_text, code_content, openai_key, model_choice)
                        elif "claude" in model_choice:
                            result = analyze_with_anthropic(prompt_text, code_content, anthropic_key, model_choice)
                        elif "gemini" in model_choice:
                            result = analyze_with_gemini(prompt_text, code_content, gemini_key, model_choice)
                        
                        # Save to db
                        save_scan(file.name, model_choice, json.dumps(result), prompt_text)
                        
                        st.subheader(f"Results for {file.name}")
                        
                        results_list = result if isinstance(result, list) else [result]
                        for i, res in enumerate(results_list):
                            st.markdown(f"**Vulnerability:** `{res.get('vulnerability', 'N/A')}`")
                            st.markdown(f"**Line:** `{res.get('line', 'N/A')}`")
                            st.markdown("**Reasoning (Click top-right to copy):**")
                            st.code(res.get('reasoning', ''), language="markdown")
                            if i < len(results_list) - 1:
                                st.divider()
                        
                    except Exception as e:
                        st.error(f"Error analyzing {file.name}: {str(e)}")
                        
    with tab2:
        st.header("Analysis History")
        if st.button("Refresh History"):
            pass # Reruns the frame to update the load_history calls
            
        history_df = load_history()
        if not history_df.empty:
            for index, row in history_df.iterrows():
                with st.expander(f"📄 {row['filename']} | 🤖 {row['model']} | 🕒 {row['timestamp']}", expanded=False):
                    try:
                        prompt_str = row.get('prompt', '')
                        if pd.notna(prompt_str) and prompt_str:
                            with st.expander("Show Prompt", expanded=False):
                                st.code(prompt_str, language="markdown")
                                
                        res_data = json.loads(row['result_json'])
                        items = res_data if isinstance(res_data, list) else [res_data]
                        
                        for i, res in enumerate(items):
                            if not isinstance(res, dict):
                                res = {"reasoning": str(res)}
                            st.markdown(f"**Vulnerability:** `{res.get('vulnerability', 'N/A')}`")
                            st.markdown(f"**Line:** `{res.get('line', 'N/A')}`")
                            st.markdown("**Reasoning (Click top-right to copy):**")
                            st.code(res.get('reasoning', ''), language="markdown")
                            if i < len(items) - 1:
                                st.divider()
                    except Exception as e:
                        st.write("Raw JSON:")
                        st.code(row['result_json'], language="json")
        else:
            st.info("No scan history found.")

if __name__ == "__main__":
    main()
