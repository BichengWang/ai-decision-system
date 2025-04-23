import openai
import json
import os


def prompt_gen(template_md_path, basic_info_md_path, target_md_path):
    """
    Generate the prompt for the letter.
    """
    with open(template_md_path, 'r') as file:
        template_md = file.read()

    with open(basic_info_md_path, 'r') as file:
        basic_info_md = file.read()

    prompt = template_md.format(basic_info_md)

    with open(target_md_path, 'w') as file:
        file.write(prompt)


def generate_document_with_openai(input_data, instruction, api_key=None, model="gpt-4.1"):
    """
    Use OpenAI API to generate a document based on input_data and instruction.
    All input is sent as JSON, and output is expected as JSON.
    """
    if api_key:
        openai.api_key = api_key

    # Prepare the payload as JSON
    payload = {
        "instruction": instruction,
        "input": input_data,
    }
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant that generates documents based on JSON input and instructions. Respond with a JSON object containing the generated document in a 'document' field."
        },
        {
            "role": "user",
            "content": json.dumps(payload)
        }
    ]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0.8
    )
    # Extract the JSON from the response
    content = response['choices'][0]['message']['content']
    try:
        output_json = json.loads(content)
    except Exception:
        # If the model returns markdown or code block, try to extract JSON
        import re
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            output_json = json.loads(match.group(0))
        else:
            raise ValueError("OpenAI response did not contain valid JSON.")
    return output_json


if __name__ == "__main__":
    template_md_path = "prompt.md"
    basic_info_md_path = "basic_info.md"
    target_md_path = "target.md"
    prompt_gen(template_md_path, basic_info_md_path, target_md_path)
    api_key = os.getenv("OPENAI_API_KEY")
    input_data = {}
    instruction = open(target_md_path, 'r').read()
    output = generate_document_with_openai(input_data, instruction, api_key)
    print(output)
