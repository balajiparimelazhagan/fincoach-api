from google.adk.agents.llm_agent import Agent

transaction_extractor_agent = Agent(
    model='gemini-2.5-flash',
    name='transaction_extractor_agent',
    description='A specialized agent for extracting financial transaction details from email content.',
    instruction='You are a highly skilled financial transaction extractor. Your task is to extract transaction details (amount, type, date, description, source, and confidence score) from email subjects and bodies related to bank transactions. Focus on identifying key phrases, numbers, and dates that indicate financial activity. If you cannot extract a specific piece of information, indicate it clearly.',
)
