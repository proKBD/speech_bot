import speech_recognition as sr
import pyttsx3
import threading
import queue
import time
import google.generativeai as genai
from dotenv import load_dotenv
import os

class SpeechBot:
    def __init__(self):
        # Initialize speech recognition
        self.recognizer = sr.Recognizer()
        
        # List available microphones
        print("Available microphones:")
        for index, name in enumerate(sr.Microphone.list_microphone_names()):
            print(f"Microphone {index}: {name}")
        
        # Initialize microphone - use Microphone Array (Intel Smart Sound Technology)
        try:
            # Find the index of the Intel Smart Sound Technology microphone
            mic_index = None
            for index, name in enumerate(sr.Microphone.list_microphone_names()):
                if "Intel" in name and "Smart" in name and "Microphone" in name:
                    mic_index = index
                    break
            
            if mic_index is not None:
                self.microphone = sr.Microphone(device_index=mic_index)
                print(f"Using microphone: {sr.Microphone.list_microphone_names()[mic_index]}")
            else:
                # Fall back to default microphone if Intel mic not found
                self.microphone = sr.Microphone()
                print(f"Using default microphone: {self.microphone.device_index}")
        except Exception as e:
            print(f"Error initializing microphone: {e}")
            raise
        
        # Initialize text-to-speech engine
        self.engine = None
        self.init_tts_engine()
        
        # List available voices
        print("\nAvailable voices:")
        voices = self.engine.getProperty('voices')
        for idx, voice in enumerate(voices):
            print(f"Voice {idx}: {voice.name} ({voice.id})")
        
        # Set voice (default to the first voice)
        if voices:
            # You can change the index to select a different voice
            # 0 is usually a male voice, 1 is usually a female voice
            self.engine.setProperty('voice', voices[1].id)  # Change to index 1 for female voice
            print(f"Using voice: {voices[1].name}")
        
        # Set speech rate
        self.engine.setProperty('rate', 150)  # Speed of speech
        
        # Initialize Gemini
        load_dotenv()
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        # Use Gemini 2.0 Flash model
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Initialize queues for handling interruptions
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        
        # Flag to control the conversation flow
        self.is_speaking = False
        self.should_stop = False
        
        # Conversation history
        self.conversation_history = []
        
        # Lock for thread synchronization
        self.speech_lock = threading.Lock()
        
    def init_tts_engine(self):
        """Initialize or reinitialize the text-to-speech engine"""
        try:
            # If engine exists, stop it first
            if self.engine:
                try:
                    self.engine.stop()
                except:
                    pass
            
            # Create a new engine instance
            self.engine = pyttsx3.init()
            
            # Set voice (default to the first voice)
            voices = self.engine.getProperty('voices')
            if voices:
                # You can change the index to select a different voice
                # 0 is usually a male voice, 1 is usually a female voice
                self.engine.setProperty('voice', voices[1].id)  # Change to index 1 for female voice
                print(f"Using voice: {voices[1].name}")
            
            # Set speech rate
            self.engine.setProperty('rate', 150)  # Speed of speech
            
            # Test the engine with a simple phrase
            test_text = "Testing voice engine"
            self.engine.say(test_text)
            self.engine.runAndWait()
            
            return True
            
        except Exception as e:
            print(f"Error initializing TTS engine: {e}")
            self.engine = None
            return False
        
    def listen(self, interrupt_mode=False):
        """Listen to user input and convert speech to text"""
        # Create a new microphone instance for each listen call
        mic = sr.Microphone(device_index=self.microphone.device_index)
        
        with mic as source:
            if interrupt_mode:
                print("Listening for interruption...")
            else:
                print("Listening...")
            try:
                print("Adjusting for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                print("Ready to capture audio...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                print("Audio captured, converting to text...")
                text = self.recognizer.recognize_google(audio)
                print(f"You said: {text}")
                return text
            except sr.WaitTimeoutError:
                print("Timeout waiting for audio input")
                return None
            except sr.UnknownValueError:
                print("Could not understand audio")
                return None
            except sr.RequestError as e:
                print(f"Could not request results; {e}")
                return None
            except Exception as e:
                print(f"Unexpected error in listen(): {e}")
                return None

    def get_llm_response(self, user_input):
        """Get response from Gemini"""
        try:
            print(f"Sending to Gemini: {user_input}")
            
            # Add user input to conversation history
            self.conversation_history.append({"role": "user", "content": user_input})
            
            # Create a prompt that includes conversation history
            prompt = "You are a helpful AI assistant. Keep your responses concise and natural.\n\n"
            for item in self.conversation_history[-5:]:  # Include last 5 exchanges
                if item["role"] == "user":
                    prompt += f"User: {item['content']}\n"
                else:
                    prompt += f"Assistant: {item['content']}\n"
            
            prompt += f"User: {user_input}\nAssistant:"
            
            response = self.model.generate_content(prompt)
            
            # Handle the response properly
            if response and hasattr(response, 'parts'):
                result = response.parts[0].text.strip()
                print(f"Gemini response: {result}")
                # Add assistant response to conversation history
                self.conversation_history.append({"role": "assistant", "content": result})
                return result
            elif response and hasattr(response, 'text'):
                result = response.text.strip()
                print(f"Gemini response: {result}")
                # Add assistant response to conversation history
                self.conversation_history.append({"role": "assistant", "content": result})
                return result
            else:
                error_msg = "I apologize, but I couldn't generate a proper response."
                print("No valid response from Gemini")
                self.conversation_history.append({"role": "assistant", "content": error_msg})
                return error_msg
        except Exception as e:
            print(f"Error getting Gemini response: {e}")
            error_msg = "I apologize, but I'm having trouble processing your request."
            self.conversation_history.append({"role": "assistant", "content": error_msg})
            return error_msg

    def speak(self, text):
        """Convert text to speech"""
        with self.speech_lock:
            try:
                print(f"Speaking: {text}")
                self.is_speaking = True
                self.should_stop = False
                
                # Start a thread to listen for interruptions while speaking
                interrupt_thread = threading.Thread(target=self.listen_for_interruptions)
                interrupt_thread.daemon = True
                interrupt_thread.start()
                
                # Initialize a new engine instance for each speech
                try:
                    # Create a new engine instance
                    engine = pyttsx3.init()
                    
                    # Set voice
                    voices = engine.getProperty('voices')
                    if voices:
                        engine.setProperty('voice', voices[1].id)  # Use female voice
                    
                    # Set speech rate
                    engine.setProperty('rate', 150)
                    
                    # Speak the text
                    engine.say(text)
                    engine.runAndWait()
                    
                except Exception as e:
                    print(f"Error in speech engine: {e}")
                    # Try one more time with a new engine
                    try:
                        engine = pyttsx3.init()
                        engine.say(text)
                        engine.runAndWait()
                    except:
                        print("Failed to speak after retry")
                
                # Stop the interruption thread
                self.should_stop = True
                self.is_speaking = False
                
                print("Ready for next input...")
            except Exception as e:
                print(f"Error in speak(): {e}")
                self.is_speaking = False
                self.should_stop = True

    def listen_for_interruptions(self):
        """Listen for user interruptions while the bot is speaking"""
        while self.is_speaking and not self.should_stop:
            try:
                # Listen for interruption
                interruption = self.listen(interrupt_mode=True)
                if interruption:
                    print(f"Interruption detected: {interruption}")
                    
                    # Set flags to stop the current speech
                    self.should_stop = True
                    
                    # Stop the current speech
                    with self.speech_lock:
                        try:
                            # Process the interruption
                            response = self.get_llm_response(interruption)
                            
                            # Wait a moment to ensure the previous speech is fully stopped
                            time.sleep(0.5)
                            
                            # Reset flags
                            self.is_speaking = False
                            
                            # Speak the response to the interruption
                            if response:
                                print(f"Speaking interruption response: {response}")
                                try:
                                    # Create a new engine instance for the response
                                    engine = pyttsx3.init()
                                    voices = engine.getProperty('voices')
                                    if voices:
                                        engine.setProperty('voice', voices[2].id)
                                    engine.setProperty('rate', 150)
                                    engine.say(response)
                                    engine.runAndWait()
                                except Exception as e:
                                    print(f"Error speaking interruption response: {e}")
                                    # Try one more time
                                    try:
                                        engine = pyttsx3.init()
                                        engine.say(response)
                                        engine.runAndWait()
                                    except:
                                        print("Failed to speak interruption response after retry")
                        except Exception as e:
                            print(f"Error handling interruption: {e}")
                    break
            except Exception as e:
                print(f"Error in interruption handling: {e}")
                time.sleep(0.1)

    def run(self):
        """Main conversation loop"""
        print("Speech Bot is ready! Press Ctrl+C to exit.")
        print("You can interrupt the bot at any time by speaking while it's responding.")
        
        while True:
            try:
                # Listen for user input
                user_input = self.listen()
                if not user_input:
                    continue

                # Get response from Gemini
                response = self.get_llm_response(user_input)
                
                # Ensure we have a valid response
                if response:
                    # Always speak the response
                    try:
                        print(f"Speaking response: {response}")
                        # Create a new engine instance for the response
                        engine = pyttsx3.init()
                        voices = engine.getProperty('voices')
                        if voices:
                            engine.setProperty('voice', voices[1].id)
                        engine.setProperty('rate', 150)
                        engine.say(response)
                        engine.runAndWait()
                    except Exception as e:
                        print(f"Error speaking response: {e}")
                        # Try one more time
                        try:
                            engine = pyttsx3.init()
                            engine.say(response)
                            engine.runAndWait()
                        except:
                            print("Failed to speak response after retry")
                else:
                    # If no response, speak a fallback message
                    try:
                        print("Speaking fallback message")
                        engine = pyttsx3.init()
                        engine.say("I apologize, but I couldn't generate a response. Could you please try again?")
                        engine.runAndWait()
                    except:
                        print("Failed to speak fallback message")
                
                # Reset flags
                self.should_stop = False
                self.is_speaking = False
                
                # Add a small delay before listening again
                time.sleep(0.5)
                
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"An error occurred: {e}")
                # Try to speak the error message
                try:
                    engine = pyttsx3.init()
                    engine.say("I encountered an error. Please try again.")
                    engine.runAndWait()
                except:
                    print("Failed to speak error message")
                continue

if __name__ == "__main__":
    bot = SpeechBot()
    bot.run() 