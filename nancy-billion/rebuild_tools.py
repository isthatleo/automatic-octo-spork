import sys

def rebuild_tools_py():
    try:
        # Read all the parts
        with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\backend\\tools_up_to_security_hardening.py", "r", encoding="utf-8") as f:
            part1 = f.read()
        
        with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\learning_tool_functions.py", "r", encoding="utf-8") as f:
            part2 = f.read()
            
        with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\learning_tool_registrations.py", "r", encoding="utf-8") as f:
            part3 = f.read()
            
        with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\backend\\tools_last3.py", "r", encoding="utf-8") as f:
            part4 = f.read()
        
        # Combine them
        combined = part1 + part2 + part3 + part4
        
        # Write the final file
        with open("C:\\Users\\leona.DESKTOP-10QNDAN\\Desktop\\automatic-octo-spork\\nancy-billion\\backend\\tools.py", "w", encoding="utf-8") as f:
            f.write(combined)
            
        print("Successfully rebuilt tools.py")
        return True
        
    except Exception as e:
        print(f"Error rebuilding tools.py: {e}")
        return False

if __name__ == "__main__":
    rebuild_tools_py()