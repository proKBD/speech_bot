# Speech Bot with Interruption Support

A conversational AI assistant that can be controlled by voice and supports user interruptions.

## Features

- **Voice Control**: Speak to the bot and receive spoken responses
- **User Interruptions**: Interrupt the bot at any time during its response
- **Visual Interface**: See the conversation history and control the bot through a GUI
- **Voice Customization**: Select different voices and adjust speech rate
- **Conversation History**: View the entire conversation in the GUI

## Requirements

- Python 3.8 or higher
- Microphone
- Speakers or headphones
- Google API key for Gemini AI

## Installation

1. Clone this repository
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project root with your Google API key:
   ```
   GOOGLE_API_KEY=your_api_key_here
   ```

## Usage

1. Run the speech bot:
   ```
   python speech_bot.py
   ```

2. The GUI will appear with the following controls:
   - **Start Conversation**: Begin speaking with the bot
   - **Stop**: End the current conversation
   - **Voice Settings**: Select a different voice and adjust speech rate

3. During a conversation:
   - Speak to ask questions or give commands
   - The bot will respond verbally and display the conversation in the GUI
   - You can interrupt the bot at any time by speaking while it's responding

## Troubleshooting

- **Microphone Issues**: If the bot doesn't detect your microphone, check the console output for available microphones and modify the code to use a different one.
- **Voice Issues**: If you don't hear the bot speaking, check your audio settings and make sure the correct output device is selected.
- **API Key Issues**: Ensure your Google API key is correctly set in the `.env` file and has access to the Gemini API.

## License

MIT 