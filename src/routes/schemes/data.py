# we import the base model as it is the main structure for any scheme  
# we call the class process request to specify that it is the class of end points requests
# it should inherit from the base model to be able to use its features and functionalities 
# we specify the attributes of the class and their types to ensure that the data is in the correct format and to enable validation
# we use from typing import Optional to allow for optional attributes that may not be required in every request like chunk size
# we added post request to data.py to handle file processing
# we need to make contoller for this end point to handle the logic of processing the file and returning the response
# we use langchain to use library for pdf processing and text extraction
# we made two functions in it get file extension and get file loader 
# we use different loaders for different file types to ensure that we can handle a variety of file formats and extract the necessary information from them and also langchain provides a unified interface for working with different file types, making it easier to implement the file processing logic in our controller
# put file types in enum to make it easy access
# then we make function for loading the content which is loader.load() and we return the content as a list of documents which can be further processed or returned in the response 
# when the prompt is written we need to compare the content of the files to know which is near to the prompt and for that we use vector search but we need to recieve the content in the form of chunks to be able to process it and compare it to the prompt effectively and for that we use chunk size as an optional attribute in the request model to allow for flexibility in how the content is processed and compared to the prompt.
# there are specified text splitters in lang chain 
# i need to know 
# 1- how to connect to the db 2- how to get the chunks from the db 
# when i have multiple types of thing and they use same thing we use factory design pattern 