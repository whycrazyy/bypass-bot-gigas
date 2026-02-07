import os, jwt, json

token = os.environ.get("TOKEN")
if not token:
    raise SystemExit("export TOKEN='eyJhbGciOiJIUzI1NiJ9.eyJYLUNIQU5ORUwiOiJXRUIiLCJYLVRPS0VOLVZFUlNJT04iOiIxLjAuMCIsIlgtVVNFUi1JRCI6IjkyOTkyOTE2NTIxIiwiWC1XQUxMRVQtSUQiOiJlNGQ1ZDUyMjY3ODIiLCJleHAiOjE3NzcyNTM2ODMsImlhdCI6MTc2OTQ3NzY4MywiaXNzIjoiY1k3OG4zaGV1a3l3YTRoelB1OFh4UHFOTVhoTUNCMjQiLCJzdWIiOiI5Mjk5MjkxNjUyMSJ9.dxzVchhbLBD_Jqym0EOrv_Bq9YiXxZJSdyfh6lczZ-M'")

payload = jwt.decode(token, options={"verify_signature": False})
print(json.dumps(payload, indent=2, ensure_ascii=False))