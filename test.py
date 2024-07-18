from myllm import Qwen2
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
from langchain_core.prompts import ChatPromptTemplate


llm = Qwen2()

# loader = UnstructuredWordDocumentLoader("C:\重要文档\实验报告\软件工程\project-zju\langchain\第一章-基础知识.docx")
# docs = loader.load()

# text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
# splits = text_splitter.split_documents(docs)
vectorstore = Chroma(persist_directory="./db", embedding_function=HuggingFaceEmbeddings())

# Retrieve and generate using the relevant snippets of the blog.
retriever = vectorstore.as_retriever()

system_prompt = (
    """
    基于以下已知信息，简洁和专业的来回答用户的问题。
    如果无法从中得到答案，请说 "根据已知信息无法回答该问题" 
    或 "没有提供足够的相关信息"，不允许在答案中添加编造成分，
    答案请使用中文。已知内容:"{context}"""
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{question}"),
    ]
)

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

for chunk in rag_chain.stream("感冒了怎么办"):
    print(chunk, end="", flush=True)