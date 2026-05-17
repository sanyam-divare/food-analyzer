
from google import genai

import os



# 1. Grab your code file

with open("app.py", "r") as f:

    code_content = f.read()



# 2. Fire the direct API request using Flash

client = genai.Client(api_key=os.environ.get("AIzaSyAObchBd_L_K3P9vrxkxvSQXMJ3xY-XEpE"))

response = client.models.generate_content(

    model='gemini-2.5-flash',

    contents=f"Review this app script and suggest improvements for parsing food data:\n\n{code_content}",

)



print(response.text)

