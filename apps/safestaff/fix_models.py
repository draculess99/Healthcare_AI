import os

file_path = 'd:/Work/Springboard/ANTIGRAVITY-SCRATCH/day2/agy-cli-projects-2/ER-Wait-Time/nurse_staffing_system- github-GROQ/SafeStaff_AI-main/frontend/dashboard.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

target_str = 'st.session_state.get("model_option", "gemini-2.0-flash")'
replacement_str = '(os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash"))'

content = content.replace(target_str, replacement_str)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Replaced successfully")
