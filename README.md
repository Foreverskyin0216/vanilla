# Vanilla

Vanilla is a simple chatbot that can role-play as a cute catgirl.

## 🚀 Getting Started

Clone the repository and install the dependencies

```bash
git clone <repository>
cd <repository>
npm install
```

Run the following command to set up the environment variables.

```bash
cp .env.example .env
```

Edit the `.env` file with the required environment variables.

```bash
# Set the name of the catgirl. Default is "香草".
CATGIRL_NAME=<Your Catgirl Name>

# Enable "Log in with password" and "Letter Sealing" for use with your LINE SelfBot.
LINE_EMAIL=<Your LINE Email>
LINE_PASSWORD=<Your LINE Password>

# Obtain the OpenAI API Key for use with the OpenAI API.
# Reference: https://platform.openai.com/docs/api-reference/authentication
OPENAI_API_KEY=<Your OpenAI API Key>

# Set the API endpoint for the OpenAI API if you are using a custom endpoint.
# OPENAI_API_ENDPOINT=<Your OpenAI API Endpoint>

# Obtain the Tavily API Key for use with the Tavily API. (Used for searching any information)
# Reference: https://tavily.com/
TAVILY_API_KEY=<Your Tavily API Key>
```

Run the application

```bash
npm run start
```

Enter the pincode sent to your LINE application.(Default pincode is `114514`)

## 📚 Reference

- https://linejs.evex.land/
- https://langchain-ai.github.io/langgraphjs/
- https://js.langchain.com/docs/introduction/
