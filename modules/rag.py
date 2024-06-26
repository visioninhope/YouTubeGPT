import logging
import uuid
from typing import List, Literal

from chromadb import Collection
from langchain.chat_models.base import BaseChatModel
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from modules.helpers import num_tokens_from_string

CHUNK_SIZE_FOR_UNPROCESSED_TRANSCRIPT = 512


embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

RAG_SYSTEM_PROMPT = """You are a helpful assistant, skilled in answering questions and providing information about a topic.

You are going to reiceive excerpts from a video transcript as context. Furthermore a user will provide a question or a topic. 
If you receive a question, give a detailed answer. If you receive a topic, tell the user what is said about the topic. 
In either case, keep your answer ground in the facts of the context.
If the context does not contain the facts to answer the question, apologize and say that you don't know the answer.
"""

rag_user_prompt = PromptTemplate.from_template(
    """Context: {context}
---          
Here is the users question/topic: {question}
"""
)

rag_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", RAG_SYSTEM_PROMPT),
        ("user", "{input}"),
    ]
)


def split_text_recursively(
    transcript_text: str,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
    len_func: Literal["characters", "tokens"] = "characters",
):
    """Splits a string recurisively by characters or tokens."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len if len_func == "characters" else num_tokens_from_string,
    )
    splits = text_splitter.create_documents([transcript_text])
    logging.info(
        f"Split transcript into {len(splits)} chunks with a provided chunk size of {chunk_size} tokens."
    )
    return splits


def format_docs_for_context(docs):
    return "\n\n---\n\n".join(doc.page_content for doc in docs)


def embed_excerpts(collection: Collection, excerpts: List[Document]):
    """If there are no embeddings in the database, each document in the list is embedded in the provided collection."""
    if collection.count() <= 0:
        for e in excerpts:
            response = embeddings.embed_query(e.page_content)
            collection.add(
                ids=[str(uuid.uuid1())],
                embeddings=[response],
                documents=[e.page_content],
            )


def find_relevant_documents(query: str, db: Chroma):
    retriever = db.as_retriever(search_kwargs={"k": 3})
    return retriever.invoke(input=query)


def generate_response(question: str, llm: BaseChatModel, relevant_docs: List[Document]):
    formatted_input = rag_user_prompt.format(
        question=question, context=format_docs_for_context(relevant_docs)
    )
    rag_chain = rag_prompt | llm | StrOutputParser()
    return rag_chain.invoke({"input": formatted_input})
