from core.agent import Agent

with open("system_prompt.txt", "r", encoding="utf-8") as prompt_file:
    agent = Agent(prompt_file.read())
    agent.run()
