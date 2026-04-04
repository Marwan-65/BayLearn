from abc import ABC , abstractmethod
# abc is the Abstract Base Class module in Python, which provides a way to define abstract classes and methods. 
# An abstract class cannot be instantiated and is meant to be subclassed.
# An abstract method is a method that is declared but contains no implementation. 
# Subclasses of an abstract class must implement all abstract methods.
# abstract method is a decorator that can be used to declare a method as abstract, meaning that it must be implemented by any subclass of the abstract class.
# decorator means a function that takes another function as an argument and extends its behavior without explicitly modifying it.
# LLM is used for converting text into vectors and for generating responses based on the input text.
# Each interface will have enum for any constants that are used in the interface to ensure that they are easily accessible and maintainable.

class LLMInterface(ABC):
    @abstractmethod
    def set_generation_model(self,model_id:str):
        pass
    @abstractmethod
    def set_embedding_model(self,model_id:str,embedding_size:int):
        pass
    @abstractmethod
    # the generate_text method is used to generate a response based on the input prompt, the maximum number of tokens to generate, and an optional temperature parameter that controls the randomness of the generated text.
    # after this function prompt will be sent to construct prompt to be formatted in a way that is suitable for the specific LLM being used and then the formatted prompt will be sent to the generate function of the LLM to generate the response based on the input prompt and the specified parameters.
    def generate_text(self,prompt:str,chat_history:list=[],max_output_tokens:int=None,temperature:float = None):
        pass
    @abstractmethod
    # the embed_text method is used to convert text into a vector representation that can be stored in a vector database and used for similarity search and other operations.
    def embed_text(self,text:str,document_type:str):
        pass

    def embed_texts_batch(self, texts: list, document_type: str) -> list:
        """Embed multiple texts at once. Providers can override for true batch encoding."""
        return [self.embed_text(t, document_type) for t in texts]
    @abstractmethod
    # the construct_prompt method is used to construct a prompt for generating a response based on the input prompt and the role of the user (e.g., system, user, assistant). This method can be used to format the prompt in a way that is suitable for the specific LLM being used.
    def construct_prompt(self,prompt: str, role: str):
        pass
   