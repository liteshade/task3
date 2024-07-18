from typing import Any, Dict, Iterator, List, Mapping, Optional
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM
from langchain_core.outputs import GenerationChunk
import requests
import json

class Qwen2(LLM):
    chat_history:Any
    
    @property
    def _llm_type(self) -> str:
        return "Qwen2"
    
    #将读取的流式传输转换为json
    def __ParseRespJson__(self,chunk):
        json_strings = chunk.strip().split('\n\n')
        json_objects = []
        for json_str in json_strings:
            

            if json_str.startswith('data: '):
                json_str = json_str[6:]  # 去掉前缀 'data: '
                #结束符，单独拿出来
                if json_str == "[DONE]":
                    return True
                try:
                    json_obj = json.loads(json_str)
                    json_objects.append(json_obj)
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON: {e}")
                    continue
        
        return json_objects

    #直接传输
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        if stop is not None:
            raise ValueError("stop kwargs are not permitted.")
        return prompt[: self.n]

    #流式传输
    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[GenerationChunk]:
        
        # headers中添加上content-type这个参数，指定为json格式
        headers = {'Content-Type': 'application/json'}
        record = str(self.chat_history.format_chat_history())
        prompt = 'System: \n 聊天记录：' + record + prompt[7:]
        
        data = {"model": "Qwen/Qwen2-7B-Instruct",
                "messages": [{"role": "user", "content": prompt}],
                "stream":"True"}
        print(data)
        
        response = requests.post("http://101.200.242.185:7120/v1/chat/completions", json=data, headers=headers, stream=True)
        
        if response.status_code == 200:
            for chunks in response.iter_content(chunk_size=512):
                if chunks:
                    chunks = chunks.decode('utf-8')  # 处理每个数据块
                    chunks = self.__ParseRespJson__(chunk=chunks)
                    #表明传输已经结束
                    if chunks == True:
                        return
                    for chunk in chunks:
                        try:
                            resp_word = chunk["choices"][0]["delta"]["content"]
                            mychunk = GenerationChunk(text=resp_word)
                            yield(mychunk)
                        except:
                            pass
          
if __name__ == '__main__':
    llm = Qwen2()

