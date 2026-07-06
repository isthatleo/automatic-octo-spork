# Read the file, fix the issues, and write it back
with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\learning_section.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the problem_domain.lower() issues
content = content.replace('if "energy" in problem_domain.lower() or "power" in problem_domain.lower():', 'if "energy" in str(problem_domain).lower() or "power" in str(problem_domain).lower():')
content = content.replace('elif "health" in problem_domain.lower() or "medical" in problem_domain.lower():', 'elif "health" in str(problem_domain).lower() or "medical" in str(problem_domain).lower():')

# Write the fixed content back
with open("C:\\Users\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\learning_section.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed invention_engine function")