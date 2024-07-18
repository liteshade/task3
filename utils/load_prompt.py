from langchain_core.prompts import ChatPromptTemplate
def load_prompt():
    system_prompt = (
        """
        已知内容:"{context} 基于聊天记录和已知内容，简洁和专业的来回答用户的问题。如果无法从已知内容中得到答案，请从聊天记录中查找。若找不到答案，请说 "根据已知信息无法回答该问题" 或 "没有提供足够的相关信息"。不允许在答案中添加编造成分，请使用中文。"""
    )
    
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "{question}"),
        ]
    )
    
    return prompt