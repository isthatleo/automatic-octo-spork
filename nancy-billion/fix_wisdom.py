# Read the file, fix the issues, and write it back
with open("C:\\Users\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\learning_section.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the experience_description.lower() issues
content = content.replace('if "team" in experience_description.lower() or "conflict" in experience_description.lower() or "leadership" in experience_description.lower():', 'if "team" in str(experience_description).lower() or "conflict" in str(experience_description).lower() or "leadership" in str(experience_description).lower():')
content = content.replace('elif "learning" in experience_description.lower() or "skill" in experience_description.lower() or "education" in experience_description.lower():', 'elif "learning" in str(experience_description).lower() or "skill" in str(experience_description).lower() or "education" in str(experience_description).lower():')

# Write the fixed content back
with open("C:\\Users\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\learning_section.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed wisdom_distillation function")