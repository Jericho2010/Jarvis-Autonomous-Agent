from prompt_toolkit.styles import Style

try:
    style = Style.from_dict({
        "bottom-toolbar": "bg:#4A0000 #FFD700 bold"
    })
    print("Style 1 valid")
except Exception as e:
    print(f"Style 1 error: {e}")

try:
    style = Style.from_dict({
        "bottom-toolbar": "bg:#4A0000 fg:#FFD700 bold"
    })
    print("Style 2 valid")
except Exception as e:
    print(f"Style 2 error: {e}")
