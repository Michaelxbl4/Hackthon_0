import os
from flask import Flask, request, render_template, jsonify,session
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field
import re
import json
tokens_output=2500
api_key_list=[]
load_dotenv()
app = Flask(__name__)
app.secret_key="secretKeyforTheSite"

def get_api_key_list():
    """Read the comma-separated key list out of the session safely,
    then append the env variable key (if set) as a final fallback."""
    raw = session.get('keys', '')
    keys = [k.strip() for k in raw.split(',') if k.strip()]
    env_key = os.getenv('GEMINI_API_KEY')
    if env_key and env_key not in keys:
        keys.append(env_key)

    return keys


def generate_with_fallback(model, contents, config=None):
    """
    Try each API key in session['keys'] (plus the env var key) in order
    until one works. Returns None if every key fails, instead of raising,
    so callers can send back a graceful "no data" response.
    """
    api_key_list = get_api_key_list()

    if not api_key_list:
        print("No API keys available (session or env).")
        return None

    last_error = None
    for idx, key in enumerate(api_key_list):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model=model, contents=contents, config=config)
            print(f"Succeeded using API key #{idx + 1}")
            return response
        except Exception as e:
            print(f"API key #{idx + 1} failed: {e}")
            last_error = e
            continue

    print(f"All {len(api_key_list)} API key(s) failed. Last error: {last_error}")
    return None

def salvage_json_array(text):
    """
    Parse a '[{...}, {...}, ...]' style string one object at a time.
    If the model's response got cut off mid-object (hit max_output_tokens),
    this keeps every complete object before the cut and just drops the
    broken trailing one, instead of json.loads() throwing away everything.
    """
    start = text.find('[')
    if start == -1:
        return []

    decoder = json.JSONDecoder()
    idx = start + 1
    items = []
    while True:
        while idx < len(text) and text[idx] in ' \t\n\r,':
            idx += 1
        if idx >= len(text) or text[idx] == ']':
            break
        try:
            obj, end = decoder.raw_decode(text, idx)
            items.append(obj)
            idx = end
        except json.JSONDecodeError:
            break  # hit the truncated/broken object - stop here, keep what we have

    return items

class ExtractedFeatures(BaseModel):
    features: list[str] = Field(description="A list of specific professional roles, features, or services extracted from the text.")

@app.route('/', methods=['GET'])
def Display():
    return render_template('input.html')

@app.route('/read-form', methods=['POST'])
def read_form():
    data = request.form
    if not data:
        return {"status": "empty prompt"}
    try:
        session['keys']=data.get('api_key')
        session['model']=data.get('model','gemini-2.5-flash')
        session['link']=data.get('product_link','')
        #api_key_list=session['keys'].split(',')
        #api_key_list.append()
        print("Sending prompt to",session.get('model','gemini-2.5-flash'))
        tokens_output = int(data.get('max_tokens', 2500))
        response = generate_with_fallback( model=session['model'],contents=f"Analyze this description and extract the required features or roles: {data}", config={"response_mime_type": "application/json", "response_schema": ExtractedFeatures})
        if response is None:
            return render_template("list_items.html", items=["No Data"])

        responded = response.parsed
        return render_template("list_items.html", items=responded.features)
        #response = client.models.generate_content(
        #    model=session['model'],
        #    contents=f"Analyze this description and extract the required features or roles: {data}",
       #     config={"response_mime_type": "application/json", "response_schema": ExtractedFeatures}
        #)
        #responded = response.parsed
        #return render_template("list_items.html", items=responded.features)      
    except Exception as e:
        return f"Some error occurred: {str(e)}"       

@app.route('/process-final-selection', methods=['POST'])
def handle_final_selection():
    html=''''''
    # 1. Parse incoming raw JSON transmission data safely
    data = request.get_json()
    
    if not data:
        return "No data packet found", 400

    # 2. Extract values into standalone python variables for your custom pipeline
    extracted_items = data.get("items", [])
    selected_options = data.get("options", {})

    wants_pitch = selected_options.get("pitch", False)
    wants_links = selected_options.get("link", False)
    wants_reviews = selected_options.get("review", False)
    wants_list = selected_options.get("list", False)

    # Print statements for verification in terminal log console
    print(f"COMPANIES LIST: {extracted_items}")
    print(f"WANTS PITCH DECK TEXT: {wants_pitch}")
    print(f"WANTS SITE LINKS: {wants_links}")

    # --- YOUR CUSTOM SEARCH MODEL PIPELINE CAN GO HERE ---
    # Example: If wants_pitch is True, you can use client.models.generate_content() here!

    # 3. Create a clean dict using 'company_list' instead of 'items' to stop the Jinja crash

    # 4. Pass the payload data dictionary straight to the page template engine
    #processed_payload is correct extracted_items contains list of categories now we will pass it to ai so iyt can process it and we dislay the comapny names and different categories
    #TODO add region selector also where person cam pass geological areas or states or countries for target clients
    prompt=""
    if not wants_list:
        render_template('input.html')
        return
    if wants_list:
        prompt=(f"Perform a live web search and provide a list of active companies which may require service in these categories {extracted_items}")
        if wants_links:
            prompt += "Include linkedin links of company, founder,cofounder or ceo"
        if wants_pitch:
            prompt+="Include a pitch how to ask that specific company for for us providing that service for company"        
        if wants_reviews:
            prompt+="also add a score on 1 to 10 of likely company is to accept teh proposal"
        prompt += (
        "\nRespond ONLY with valid JSON, no prose before or after, in this exact shape:\n"
        '[{"category": "...", "company_name": "...", '
        )
        if wants_links:
            prompt += '"contact_info": "All the links found sepaared  by , if multiple", '
        if wants_pitch:
            prompt += '"pitch": "...", '
        if wants_reviews:
            prompt += '"rating": "review of how likely they are to accept reply", '
        prompt += '}]\n'
        prompt+=(f"\n Important do not break format if you cant find something just add \" No Data \"  use jason form strictly no random text like here is the list and stuff also dont mention i followed your syntax and stuff whatever you dubmit full  response would be served in json parser any mistake will throw error output should be under {tokens_output} tokens")
    try:
        print("Sending prompt to",session.get('model','gemini-2.5-flash'))
        #response=client.models.generate_content(model=session.get('model','gemini-2.5-flash'),contents=prompt,config={"tools": [{"google_search": {}}], "temperature": 0.0, "max_output_tokens": int(tokens_output),"system_instruction": "You are a professional lead generation assistant. Format output strictly as requested, avoiding any conversational preamble or small talk."})
       # ai_response = response.text #limit has been increased but too much would give too many searches error so a good plan could be to limit number of comapnies searched once this is fixed would make site beautiful score >7 green <3 red otherwise yellow outline on widget on howering magnifies slightly an ai prompt copy type button to copy pitch and stuff
        #here add json check look for }, last instance remove all the afterwards part and add ] rest next lines should be able to mange
        response = generate_with_fallback( model=session.get('model', 'gemini-2.5-flash'),contents=prompt,config={ "tools": [{"google_search": {}}], "temperature": 0.0,   "max_output_tokens": int(tokens_output),  "system_instruction": "You are a professional lead generation assistant. Format output strictly as requested, avoiding any conversational preamble or small talk." })

        if response is None:
            ai_response = '[{"category": "no Data","company_name": "No data","contact_info": "No info","pitch": "No pitch","rating": 0}]'
        else:
            ai_response = response.text
        # strip markdown code fences etc - keep only what's between the first [ and the end
        start = ai_response.find('[')
        if start != -1:
            ai_response = ai_response[start:]

        json_loaded_respone = salvage_json_array(ai_response)

        if not json_loaded_respone:
            json_loaded_respone = [{  "category": "no Data", "company_name": "No data", "contact_info": "No info", "pitch": "No pitch", "rating": 0}]
        
        
        #match = re.search(r"\[(.*)\]", ai_response, re.DOTALL)
        #ai_response = f"[{match.group(1)}]" if match else ai_response
        #print(ai_response)
       # if ai_response[-1] != ']':
           # if(ai_response.find("}")==-1):
             #   ai_response='[{"category": "no Data","company_name": "No data","contact_info": "No info","pitch": "No pitch","rating": 0}]'
            #trimmed = ai_response.rsplit('}', 1)[0]
           # if not trimmed.endswith('"'):
          #      trimmed += '"'
         #   ai_response = trimmed + '}]'
        #    print("formated\n",ai_response)
       # json_loaded_respone=json.loads(ai_response)
        for widget in json_loaded_respone:
            html+=(f'<div class="ai-company-card"><div class="card-meta"><h3 class="company-title">{widget.get('company_name','Not Loaded')}</h3><span class="category-badge">{widget.get('category','Not Loaded')}</span></div><div class="link-wrapper">')
            #html+=(f'<div class="ai-company-card"><div class="card-meta"><h3 class="company-title">{widget['company_name']}</h3><span class="category-badge">{widget['category']}</span><div class="link-wrapper">')
            links=widget.get('contact_info','No Info').split(',')
            for link in links:
                link=link.strip()
                html+=(f'<a href="{link}" target="_blank" class="pill-link">{link}</a>')
            html+=(f'</div><div class="pitch-container"><div class="pitch-actions"><button class="pitch-btn" onclick="toggleEdit(this)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>Edit</button><button class="pitch-btn" onclick="copyPitch(this)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>Copy</button></div><textarea class="pitch-field" readonly>{widget.get('pitch','No pitch available(Plese type manually)')}Link: {session.get('link','No link attached')}</textarea></div></div>')
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        ai_response="No response by ai"
        #it would make sense to remove list checkbox down the line i mean yeah its fine but it doesnt really serve any purpose    
    
    # <!-- Main Grid Card Wrapper -->
#   <div class="ai-company-card">
#     
#     <!-- Top Meta Details Line -->
#     <div class="card-meta">
#       <h3 class="company-title">A24 Film</h3>
#       <span class="category-badge">Film Making</span>
#     </div>
# 
#     <!-- Link Container Area -->
#     <div class="link-wrapper">
#       <a href="https://linkedin.com" target="_blank" class="pill-link">linkedin.com</a>
#       <a href="https://a24films.com" target="_blank" class="pill-link">a24films.com</a>
#     </div>
# 
#     <!-- Interactive Pitch Text Area Box Component -->
#     <div class="pitch-container">
#       <div class="pitch-actions">
#         <button class="pitch-btn" onclick="toggleEdit(this)">
#           <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
#           Edit
#         </button>
#         <button class="pitch-btn" onclick="copyPitch(this)">
#           <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
#           Copy
#         </button>
#       </div>
#       <!-- Textarea allows direct editing natively -->
#       <textarea class="pitch-field" readonly>A24, your innovative storytelling resonates deeply with audiences. We offer bespoke creative and strategic services to further amplify your unique cinematic vision.</textarea>
#     </div>
# 
#   </div>

    processed_payload = {
        "company_list": extracted_items,
        "options": selected_options,
        "ai_response": ai_response,
        "html":html}
    return render_template('list_processed.html', data=processed_payload)
if __name__ == '__main__':
    app.run(debug=True)
    #shift to local models from gemini
    #TODO next big feature to add local llm and also give option for gemini with diffferent model would have to use model name as a string and pass it in config 