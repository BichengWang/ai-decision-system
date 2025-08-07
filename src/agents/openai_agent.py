from agent import Agent, Runner
import asyncio
from openai import OpenAI


spanish_agent = Agent(
    name="Spanish agent",
    instructions="You only speak Spanish.",
)

english_agent = Agent(
    name="English agent",
    instructions="You only speak English",
)

triage_agent = Agent(
    name="Triage agent",
    instructions="Handoff to the appropriate agent based on the language of the request.",
    handoffs=[spanish_agent, english_agent],
)


async def main():
    result = await Runner.run(triage_agent, input="Hello? what's the weather today?")
    print(result.final_output)
    # ¡Hola! Estoy bien, gracias por preguntar. ¿Y tú, cómo estás?
    client = OpenAI()
    response = client.responses.create(
        prompt={
            "id": "pmpt_689501bd4c5c8196942b611ada7da4d707a99bf0ee0ab354",
            "version": "1"
        }
    )
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
