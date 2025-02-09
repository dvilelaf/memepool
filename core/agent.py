import importlib.util
import os
import sys
import time
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core.exceptions import InternalServerError

from core.plugin import Plugin

ROOT_DIR = Path(__file__).parent.parent
PLUGINS_DIR = ROOT_DIR / "plugins"


class Agent:
    """Agent"""

    def __init__(self, system_prompt: str):
        """Init"""
        load_dotenv(override=True)
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])

        self.system_prompt = system_prompt
        self.plugins = {}
        self.tools = []
        self.load_plugins()
        self.available_tools = self.build_tools()
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash", tools=self.tools
        )

    def load_plugins(self):
        """Load plugins"""

        for folder in os.listdir(PLUGINS_DIR):
            plugin_path = PLUGINS_DIR / folder / "plugin.py"

            if os.path.isfile(plugin_path):
                module_name = f"plugins.{folder}.plugin"

                # Import the plugin module
                spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Load the class that inherits from Plugin
                for attr_name in dir(module):
                    plugin_class = getattr(module, attr_name)
                    if (
                        isinstance(plugin_class, type)
                        and issubclass(plugin_class, Plugin)
                        and plugin_class is not Plugin
                    ):
                        self.plugins[plugin_class.NAME.lower()] = plugin_class()
                        print(f"Loaded {plugin_class.NAME} plugin")

    def build_tools(self):
        """Build available tools"""
        for plugin in self.plugins.values():
            self.tools.extend(
                [
                    getattr(plugin, attr)
                    for attr in dir(plugin)
                    if callable(getattr(plugin, attr)) and attr.endswith("_tool")
                ]
            )
        print(f"Loaded tools: {[t.__name__ for t in self.tools]}")

    def run(self):
        """Start the agent"""
        try:
            chat = self.model.start_chat()
            response_parts = None
            print("Running...")

            # Agent loop
            while True:
                # Sleep to avoid rate limits
                time.sleep(5)

                # Receive a call request
                try:
                    call_request = chat.send_message(
                        response_parts or self.system_prompt
                    )
                except InternalServerError:
                    print("Exception")
                    continue

                # Get the function call request
                method = None
                for part in call_request.parts:
                    fn = part.function_call
                    if not fn:
                        continue
                    plugin = self.plugins[fn.name.split("_")[0].lower()]
                    method = getattr(plugin, fn.name)
                    kwargs = dict(fn.args)

                if not method:
                    continue

                # Make the call
                try:
                    result = method(**kwargs)
                except Exception as e:
                    print(f"Exception while calling the function: {e}")
                    continue

                print(f"Called {fn.name}({kwargs}): {result}")

                # Build the response
                function_calls = {fn.name: result}

                response_parts = [
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fn, response={"result": val}
                        )
                    )
                    for fn, val in function_calls.items()
                ]

        except KeyboardInterrupt:
            print("Agent stopped")
