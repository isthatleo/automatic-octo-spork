# Read the file, fix the issues, and write it back
with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\learning_section.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the domain.lower() issues
content = content.replace('if domain.lower() in ["climate", "climate_science", "environmental"]:', 'if str(domain).lower() in ["climate", "climate_science", "environmental"]:')
content = content.replace('elif domain.lower() in ["finance", "economics"]:', 'elif str(domain).lower() in ["finance", "economics"]:')

# Write the fixed content back
with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\learning_section.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed hypothesis generation function")