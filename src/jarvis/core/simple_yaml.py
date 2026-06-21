"""Minimal YAML parser to avoid PyYAML dependency."""


def parse_simple_yaml(content: str) -> dict:
    result = {}
    current_section = result
    for line in content.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        line_content = line.strip()
        if ":" in line_content:
            parts = line_content.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip()
            if val.startswith(('"', "'")) and val.endswith(('"', "'")):
                val = val[1:-1]
            if val == "":
                new_dict = {}
                result[key] = new_dict
                current_section = new_dict
            else:
                if val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False
                elif val.lower() == "none":
                    val = None
                else:
                    try:
                        val = float(val) if "." in val else int(val)
                    except ValueError:
                        pass
                if indent > 0:
                    current_section[key] = val
                else:
                    result[key] = val
                    current_section = result
    return result
