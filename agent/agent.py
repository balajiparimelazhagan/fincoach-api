from google.adk.agents.llm_agent import Agent

email_parser_agent = Agent(
    model='gemini-2.5-flash',
    name='email_parser_agent',
    description='A specialized agent for parsing financial transaction details from email content.',
    instruction='You are a highly skilled financial email parser. Your task is to extract transaction details (amount, type, date, description, source, and confidence score) from email subjects and bodies related to bank transactions. Focus on identifying key phrases, numbers, and dates that indicate financial activity. If you cannot extract a specific piece of information, indicate it clearly.',
)
