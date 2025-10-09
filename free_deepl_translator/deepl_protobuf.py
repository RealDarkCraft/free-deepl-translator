import json
import blackboxprotobuf
import os

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROTO_DEF = json.loads(open(os.path.join(MODULE_DIR, "json","protobuf.json"), "r", encoding = "utf-8").read())

def build_dtype(proto_type, wanted_type):
    if not (isinstance(proto_type, dict)) or not (isinstance(wanted_type, str)):
        return None
    obj = proto_type.get(wanted_type)
    if (obj == None):
        return None
    for key, val in obj.items():
        if (val["type"] == "message"):
            obj[key]["message_typedef"] = build_dtype(proto_type, f"{val['message_type']}")
            if (obj[key]["message_typedef"] == None):
                return None
    return obj

def proto_decode(data, dtype):
    if (isinstance(dtype, str)):
        if ("deepl.pb.interactive_text_api." not in dtype):
            dtype = f"deepl.pb.interactive_text_api.{dtype}"
        dtype = build_dtype(PROTO_DEF, dtype)
        if (dtype == None):
            return None, None
    elif not (isinstance(dtype, dict)):
        return None, None
    return blackboxprotobuf.decode_message(data, dtype)
def proto_encode(data, dtype):
    if (isinstance(dtype, str)):
        if ("deepl.pb.interactive_text_api." not in dtype):
            dtype = f"deepl.pb.interactive_text_api.{dtype}"
        dtype = build_dtype(PROTO_DEF, dtype)
        if (dtype == None):
            return None
    elif not (isinstance(dtype, dict)):
        return None
    return blackboxprotobuf.encode_message(data, dtype)