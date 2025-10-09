class PropertyFunction:
    def __init__(self):
        pass
    def TextChangeOperation(self, _original_text, _new_text, _range):
        if not (isinstance(_original_text, str) or not isinstance(_new_text, str)):
            return None
        if not isinstance(_range, dict):
            _start = 0
            _end = 0
        else:
            if (isinstance(_range.get("start"), int)):
                _start = _range.get("start")
            else:
                _start = 0
            if (isinstance(_range.get("end"), int)):
                _end = _range.get("end")
            else:
                _end = 0
        _text_start = _original_text[:_start]
        _text_end = _original_text[_end:]
        return f"{_text_start}{_new_text}{_text_end}"
