import speech_recognition as sr
import pyttsx3
import threading
import queue
import time
import google.generativeai as genai
from dotenv import load_dotenv
import os
import tkinter as tk
from tkinter import ttk, scrolledtext
import pyaudio
import wave
import numpy as np
import ctypes
import sys

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
        
        # Audio engine for interruption
        self.audio = pyaudio.PyAudio()
        
        # Initialize GUI
        self.init_gui()
        
        # Thread for non-blocking speech
        self.speech_thread = None
        
    def init_gui(self):
        """Initialize the graphical user interface"""
        self.root = tk.Tk()
        self.root.title("Speech Bot")
        self.root.geometry("600x500")
        self.root.configure(bg="#f0f0f0")
        
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create conversation display
        self.conversation_display = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=15, font=("Arial", 10))
        self.conversation_display.pack(fill=tk.BOTH, expand=True, pady=10)
        self.conversation_display.config(state=tk.DISABLED)
        
        # Create status frame
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=5)
        
        # Status label
        self.status_label = ttk.Label(status_frame, text="Ready", font=("Arial", 10))
        self.status_label.pack(side=tk.LEFT)
        
        # Create control frame
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        # Start button
        self.start_button = ttk.Button(control_frame, text="Start Conversation", command=self.start_conversation)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # Stop button
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_conversation, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Voice selection
        voice_frame = ttk.LabelFrame(main_frame, text="Voice Settings")
        voice_frame.pack(fill=tk.X, pady=5)
        
        # Voice selection dropdown
        voices = self.engine.getProperty('voices')
        voice_names = [f"{voice.name} ({voice.id})" for voice in voices]
        
        ttk.Label(voice_frame, text="Select Voice:").pack(side=tk.LEFT, padx=5)
        self.voice_var = tk.StringVar()
        self.voice_var.set(voice_names[1] if len(voice_names) > 1 else voice_names[0])
        voice_dropdown = ttk.Combobox(voice_frame, textvariable=self.voice_var, values=voice_names, state="readonly", width=30)
        voice_dropdown.pack(side=tk.LEFT, padx=5)
        
        # Rate slider
        ttk.Label(voice_frame, text="Speech Rate:").pack(side=tk.LEFT, padx=5)
        self.rate_var = tk.IntVar(value=150)
        rate_slider = ttk.Scale(voice_frame, from_=100, to=200, variable=self.rate_var, orient=tk.HORIZONTAL, length=100)
        rate_slider.pack(side=tk.LEFT, padx=5)
        
        # Apply voice settings button
        apply_button = ttk.Button(voice_frame, text="Apply", command=self.apply_voice_settings)
        apply_button.pack(side=tk.LEFT, padx=5)
        
        # Conversation thread
        self.conversation_thread = None
        self.running = False
        
        # Update the GUI
        self.update_gui()
        
    def update_gui(self):
        """Update the GUI periodically"""
        try:
            # Update the conversation display with any new messages
            while not self.output_queue.empty():
                message = self.output_queue.get_nowait()
                self.conversation_display.config(state=tk.NORMAL)
                self.conversation_display.insert(tk.END, message + "\n")
                self.conversation_display.see(tk.END)
                self.conversation_display.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        
        # Schedule the next update
        self.root.after(100, self.update_gui)
        
    def start_conversation(self):
        """Start the conversation thread"""
        if not self.running:
            self.running = True
            self.conversation_thread = threading.Thread(target=self.run)
            self.conversation_thread.daemon = True
            self.conversation_thread.start()
            
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_label.config(text="Listening...")
            
            # Add a message to the conversation display
            self.output_queue.put("Bot: Hello! I'm ready to chat. You can interrupt me at any time by speaking.")
            
    def stop_conversation(self):
        """Stop the conversation thread"""
        if self.running:
            self.running = False
            self.should_stop = True
            self.is_speaking = False
            
            # Stop any ongoing speech
            if self.speech_thread and self.speech_thread.is_alive():
                self.stop_speech()
            
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="Stopped")
            
            # Add a message to the conversation display
            self.output_queue.put("Bot: Conversation stopped.")
            
    def apply_voice_settings(self):
        """Apply the selected voice settings"""
        try:
            # Get the selected voice
            voice_name = self.voice_var.get()
            voice_id = voice_name.split("(")[1].strip(")")
            
            # Set the voice
            self.engine.setProperty('voice', voice_id)
            
            # Set the rate
            self.engine.setProperty('rate', self.rate_var.get())
            
            # Test the voice
            self.output_queue.put("Bot: Testing new voice settings...")
            self.speak("Testing new voice settings.")
            
            self.output_queue.put("Bot: Voice settings applied.")
        except Exception as e:
            self.output_queue.put(f"Bot: Error applying voice settings: {e}")
        
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
                self.status_label.config(text="Listening for interruption...")
            else:
                print("Listening...")
                self.status_label.config(text="Listening...")
            try:
                print("Adjusting for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                print("Ready to capture audio...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                print("Audio captured, converting to text...")
                text = self.recognizer.recognize_google(audio)
                print(f"You said: {text}")
                self.output_queue.put(f"You: {text}")
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
            self.status_label.config(text="Getting response from AI...")
            
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
                self.status_label.config(text="Speaking...")
                
                # Start a thread to listen for interruptions while speaking
                interrupt_thread = threading.Thread(target=self.listen_for_interruptions)
                interrupt_thread.daemon = True
                interrupt_thread.start()
                
                # Start speech in a separate thread to allow for interruption
                self.speech_thread = threading.Thread(target=self._speak_thread, args=(text,))
                self.speech_thread.daemon = True
                self.speech_thread.start()
                
                # Wait for the speech thread to complete or be interrupted
                while self.speech_thread.is_alive() and not self.should_stop:
                    time.sleep(0.1)
                
                # If interrupted, stop the speech
                if self.should_stop:
                    self.stop_speech()
                
                # Stop the interruption thread
                self.should_stop = True
                self.is_speaking = False
                
                print("Ready for next input...")
                self.status_label.config(text="Ready")
            except Exception as e:
                print(f"Error in speak(): {e}")
                self.is_speaking = False
                self.should_stop = True
                self.status_label.config(text="Error")
    
    def _speak_thread(self, text):
        """Thread function for speaking text"""
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
            print(f"Error in speech thread: {e}")
            # Try one more time
            try:
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
            except:
                print("Failed to speak after retry")
    
    def stop_speech(self):
        """Stop the current speech"""
        try:
            # This is a workaround to stop pyttsx3 speech
            # It works by raising an exception in the speech thread
            if self.speech_thread and self.speech_thread.is_alive():
                # Get the thread ID
                thread_id = self.speech_thread.ident
                
                # Raise an exception in the thread
                if sys.platform == 'win32':
                    # Windows-specific code to terminate the thread
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_id), ctypes.py_object(SystemExit))
                else:
                    # For other platforms, we can't directly stop the thread
                    # We'll just set the flag and hope the thread checks it
                    self.should_stop = True
                
                # Wait for the thread to terminate
                self.speech_thread.join(timeout=1.0)
                
                # If the thread is still alive, we'll just continue
                if self.speech_thread.is_alive():
                    print("Could not stop speech thread, continuing anyway")
        except Exception as e:
            print(f"Error stopping speech: {e}")

    def listen_for_interruptions(self):
        """Listen for user interruptions while the bot is speaking"""
        while self.is_speaking and not self.should_stop and self.running:
            try:
                # Listen for interruption
                interruption = self.listen(interrupt_mode=True)
                if interruption:
                    print(f"Interruption detected: {interruption}")
                    self.output_queue.put(f"Interruption: {interruption}")
                    
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
                                self.output_queue.put(f"Bot: {response}")
                                try:
                                    # Create a new engine instance for the response
                                    engine = pyttsx3.init()
                                    voices = engine.getProperty('voices')
                                    if voices:
                                        engine.setProperty('voice', voices[1].id)
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
        
        while self.running:
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
                        self.output_queue.put(f"Bot: {response}")
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
                        self.output_queue.put("Bot: I apologize, but I couldn't generate a response. Could you please try again?")
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
                self.running = False
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

    def start(self):
        """Start the GUI main loop"""
        self.root.mainloop()

if __name__ == "__main__":
    bot = SpeechBot()
    bot.start() 