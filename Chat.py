from myllm import Qwen2
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import UnstructuredFileLoader
from langchain_community.document_loaders import DirectoryLoader
import os
from tqdm import tqdm
import pickle as pkl
from utils.load_prompt import load_prompt
import shutil
from langchain_core.messages import HumanMessage,AIMessage
import json
from langchain_core.runnables.history import RunnableWithMessageHistory

document_path = "C:\重要文档\实验报告\软件工程\project-zju\langchain\docs"
pkl_path = "C:\重要文档\实验报告\软件工程\project-zju\langchain\db"
chroma_path = "C:\\User Data\\chromas"
user_chroma_path = "./vectorstore"
pkl_file = "db.pkl"
re_load = 0
chunk_size = 1000
chunk_overlap = 100

#管理每个用户的AIchat类
class AIsessions:
    def __init__(self) -> None:  
        self.vector_dict = {}
        
    def add_user(self,username,mysql,app)->None:
        self.vector_dict[username] = AIchat(username=username,mysql=mysql,app=app)
        
    def get_user(self,username):
        if username in self.vector_dict:
            return self.vector_dict[username]
        else:
            return None
    def rm_user(self,username):
        
        self.vector_dict.pop(username, None)
        
class ChatHistory:
    def __init__(self,username,mysql,app):
        self.username = username
        self.app = app
        self.mysql = mysql
        self.chat_record = []
        #从数据库加载聊天记录
        cursor = self.mysql.connection.cursor()
        self.app.logger.debug(f'Executing SELECT chat_data FROM chat_history WHERE username = {username}')
        cursor.execute('SELECT chat_data FROM chat_history WHERE username = %s', (username,))
        chat_data = cursor.fetchone()
        cursor.close()
        if chat_data :
            self.chat_record = json.loads(chat_data[0])
    
    def get_chat_history(self):
        return self.chat_record
    
    def add_chat_history(self, chat_history:str, role:str):
        '''
        role: "user" or "ai"
        '''
        self.chat_record.append({'user': role, 'text': chat_history})
        chat_json = json.dumps(self.chat_record)
        self.app.logger.debug(f'INSERT INTO chat_history')
        print("更新数据库！")
        insert_query = "INSERT INTO chat_history (username, chat_data) VALUES (%s, %s) ON DUPLICATE KEY UPDATE chat_data = VALUES(chat_data)"
        #更新数据库
        cursor = self.mysql.connection.cursor()
        cursor.execute(insert_query, (self.username,chat_json,))
        self.mysql.connection.commit()
        cursor.close()
        
    def delete_chat_history(self):
        delete_query = "DELETE FROM chat_history WHERE username = %s"
        cursor = self.mysql.connection.cursor()
        cursor.execute(delete_query, (self.username,))
        self.mysql.connection.commit()
        cursor.close()
        
    def format_chat_history(self):
        out_chat_dict = []
        for chat_dict in self.chat_record:
            if "user" in chat_dict["user"]:
                out_chat_dict.append({"role": "user", "content": chat_dict["text"]})
            else:
                out_chat_dict.append({"role": "AI", "content": chat_dict["text"]})
        
        #最多保留20条记录     
        if len(out_chat_dict) > 20:
            out_chat_dict = out_chat_dict[len(out_chat_dict)-20:]
            
        print(out_chat_dict)
        return out_chat_dict
                
class AIchat:
    def __init__(self,username,mysql,app) -> None:  
        
        self.splits = []
        self.username = username
        self.chat_record = ChatHistory(username,mysql,app)
        self.llm = Qwen2()
        self.llm.chat_history = self.chat_record
        self.user_chroma_path = user_chroma_path + "/" + username
        
        
        if len(os.listdir(self.user_chroma_path)) == 0:
            shutil.copytree(chroma_path, self.user_chroma_path)

        print("开始读取文件")
        if not re_load:

            self.vectorstore = Chroma(persist_directory=self.user_chroma_path,
                                      embedding_function=HuggingFaceEmbeddings(),
                                      )
        else:

            with open(pkl_path + "\\" + pkl_file, 'rb') as f:
                docs = pkl.load(f)
                
            #加载切片
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            splits = text_splitter.split_documents(docs)
            print(splits[:10])
            
            #加载文档
            self.vectorstore = Chroma.from_documents(documents=splits,
                                                     embedding=HuggingFaceEmbeddings(),
                                                     ids=[split.metadata['source'] + str(idx) for idx,split in enumerate(splits)])
            
        print("读取完成！")
        self.retriever = self.vectorstore.as_retriever(search_type = "similarity_score_threshold",search_kwargs={"k":1,"score_threshold":0.1})
        self.prompt = load_prompt()

        self.rag_chain = (
            {"context": self.retriever , "question": RunnablePassthrough()}
            | self.prompt
            | self.llm
            | StrOutputParser()
        )
        
    def add_documents(self,new_doc):
        #加载loader
        loader = UnstructuredFileLoader(new_doc)
        docs = loader.load()

        #加载splitter
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        splits = text_splitter.split_documents(docs)
        self.vectorstore.add_documents(documents=splits,
                                       ids=[split.metadata['source'] + str(idx) for idx,split in enumerate(splits)],
                                       )
        
        #加载retriver
        self.retriever = self.vectorstore.as_retriever(search_type = "similarity_score_threshold",search_kwargs={"k":1,"score_threshold":0.1})

        print("新文件加载完毕！")
        
    def del_documents(self,doc_id):
        #遍历删除知识库
        print(doc_id)
        ids_lst = self.vectorstore.get()["ids"]
        print(ids_lst[:10])
        cnt = 0
        for ids in ids_lst:
            if doc_id in ids:
                self.vectorstore.delete(ids)
                cnt += 1
        self.retriever = self.vectorstore.as_retriever(search_type = "similarity_score_threshold",search_kwargs={"k":1,"score_threshold":0.1})

        print("共删除{}个文件".format(cnt))
        print("新文件删除完毕！")

    #获取聊天记录
    def get_chat_record(self):
        return self.chat_record.get_chat_history()
    
    #添加聊天记录
    def add_chat_record(self,chat_record,role):
        '''
        role: "user" or "ai"
        '''
        self.chat_record.add_chat_history(chat_record,role)
        
    def del_chat_record(self):
        self.chat_record.delete_chat_history()
    
    #回答
    def answer(self,user_input):
        ret_text = ""
        
        for chunk in self.rag_chain.stream(user_input):
            ret_text += chunk
            yield(f"data: {chunk}\n\n")
        print("结束！")
        self.add_chat_record(user_input,"user")
        self.add_chat_record(ret_text,"ai")  
            
    def __del__(self):
        pass

if __name__ == '__main__':
    #测试添加和删除文件
    aichat = AIchat()
    for chunk in aichat.answer("哈尔滨工业大学本科生学科竞赛加分项目"):
        print(chunk,end="")
    aichat.add_documents("C:\重要文档\实验报告\软件工程\project-zju\langchain\docs\哈尔滨工业大学本科生学科竞赛加分项目一览表.pdf")
    for chunk in aichat.answer("哈尔滨工业大学本科生学科竞赛加分项目"):
        print(chunk,end="")
    aichat.del_documents("C:\重要文档\实验报告\软件工程\project-zju\langchain\docs\哈尔滨工业大学本科生学科竞赛加分项目一览表.pdf")
    for chunk in aichat.answer("哈尔滨工业大学本科生学科竞赛加分项目"):
        print(chunk,end="")
    
