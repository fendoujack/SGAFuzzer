#dependent.py
# 模块：操作对象参数依赖解析，基于参数名的模糊匹配，忽略布尔型参数和枚举型参数。跳过了可选参数
# 增加了对描述字段的解析。利用NLP提取描述中的依存关系，并将解析结果保存为JSON文件。

import json
from graphql import build_client_schema, GraphQLInputObjectType, GraphQLObjectType, GraphQLNonNull, GraphQLScalarType, GraphQLEnumType, GraphQLList
from Levenshtein import distance
import re
import spacy
from spacy.lang.en.stop_words import STOP_WORDS
from concurrent.futures import ThreadPoolExecutor
from Levenshtein import distance as levenshtein_distance
# 加载 SpaCy 预训练模型
model_abs_path = "/home/kali/Music/code/v4/en_core_web_md-3.7.1.dist-info/en_core_web_md/en_core_web_md-3.7.1/"
nlp = spacy.load(model_abs_path)

# 增加一个自定义词汇表，确保这些词不会被拆分
custom_keywords = {"id", "url", "json", "api"}
#常见操作动词
common_verbs = ['create', 'update', 'delete', 'get', 'fetch', 'add', 'remove', 'assign', 'unassign', 'activate', 'deactivate', 'complete', 'cancel', 'capture', 'confirm', 'fulfill', 'refund', 'void', 'reorder', 'translate', 'bulk', 'move', 'attach', 'detach', 'send', 'set', 'place', 'apply', 'estimate', 'generate', 'handle', 'reset', 'revoke', 'award', 'destroy', 'import', 'keep', 'reassign', 'resend', 'accept', 'review', 'play', 'retry', 'unschedule', 'mark', 'restore', 'trigger', 'clear', 'convert', 'export', 'subscribe', 'increase', 'register', 'send', 'check', 'search', 'read', 'query', 'analyze', 'change', 'disable']

# 缓存描述的NLP处理结果，避免重复计算
description_cache = {}

def get_nlp_doc(description):
    if description in description_cache:
        return description_cache[description]
    doc = nlp(description.lower())
    description_cache[description] = doc
    return doc

# 加载 GraphQL introspection 查询结果文件
def load_schema(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

# 构建 GraphQL 模式对象
def build_graphql_schema(schema_json):
    return build_client_schema(schema_json['data'])

# 获取基础类型
def get_base_type(param_type):
    while hasattr(param_type, 'of_type'):
        param_type = param_type.of_type
    return param_type

# 获取基础类型名称
def get_base_type_name(param_type):
    return get_base_type(param_type).name

# 辅助函数：标准化字符串
def normalize_string(s):
    return re.sub(r'\W+', '', s).lower()

# 辅助函数：计算Levenshtein距离并进行模糊匹配
def is_similar(name1, name2, include, threshold=3):
    name1, name2 = normalize_string(name1), normalize_string(name2)
    if include:
        return distance(name1, name2) <= threshold or (name1 in name2 and len(name1) > 3) or (name2 in name1 and len(name2) > 3)
    else:
        return distance(name1, name2) <= threshold



# 识别明确的依赖关系
def extract_explicit_dependency(description):
    dependencies = []
    if description:


        doc = get_nlp_doc(description)

        def get_token_phrase(token):

            parts = [token.text.lower()]
            for child in token.children:
                if child.dep_ in ["compound", "amod", "nummod", "poss"]:
                    parts.insert(0, child.text.lower())
            return "".join(parts)

        for token in doc:
            if token.dep_ in ["pobj", "dobj", "attr", "nsubj"]:
                head = token.head
                if head.dep_ == "prep" and head.head.dep_ in ["attr", "nsubj", "ROOT"]:
                    full_token = get_token_phrase(token)
                    full_head = get_token_phrase(head.head)
                    dependencies.append((full_head, full_token))
    return dependencies

####################################################################
def extract_compound_keywords(doc):
    keywords = []
    for token in doc:
        # 如果是名词或者专有名词，并且有修饰词
        if token.pos_ in ['NOUN', 'PROPN']:
            compound_token = [token.text]
            for child in token.children:
                if child.dep_ in ["compound", "amod", "nummod", "poss"]: # 复合词、修饰词
                    compound_token.insert(0, child.text)
            keywords.append(" ".join(compound_token))
    return list(set(keywords))

def extract_keywords_with_phrases(description):
    # 对描述进行NLP处理
    doc = get_nlp_doc(description.lower())
    # 提取复合名词和专有名词短语
    keywords = extract_compound_keywords(doc)
    return keywords

def extract_keywords_no_modifiers(description):
    # 对描述进行NLP处理
    doc = nlp(description.lower())
    
    # 提取非修饰性的名词和专有名词，去除重复项
    keywords = list({token.text for token in doc if token.pos_ in ['NOUN', 'PROPN'] and token.dep_ not in ['amod', 'compound'] and token.text not in STOP_WORDS})
    
    return keywords

def preprocess_description(description):

    # 移除 \n 及之后的内容
    description = re.sub(r'\n.*', '', description)

    # 只保留第一句话
    description = description.split('.')[0].strip()
    description = description.split(',')[0].strip()

    for keyword in custom_keywords:
        description = re.sub(rf'\b{keyword}\b', keyword.upper() + "_TOKEN", description, flags=re.IGNORECASE)

    # 返回预处理后的描述
    return description.strip()

def extract_explicit_dependency2(description):
    flattened_dependencies = []  # 在开始时定义空列表
    if description:
        # 先进行预处理
        description = preprocess_description(description)
        if not description:
            return flattened_dependencies  # 如果没有有效描述，返回空列表

        doc = get_nlp_doc(description)

        def get_token_phrase(token):
            # 提取 token 以及其修饰词，但以独立形式返回
            if token.text.lower() in custom_keywords:
                return [token.text.lower()]
            parts = [token.text.lower()]
            for child in token.children:
                if child.dep_ in ["compound", "amod", "nummod", "poss", "prep", "dobj"]:
                    parts.append(child.text.lower())
            return parts
        
        # 提取名词和专有名词的依赖
        dependencies = [([token.text.lower()], []) for token in doc if token.pos_ in ["NOUN", "PROPN"]]

        # 将关键词展平为独立的词，以确保所有词语都被单独记录
        for head, token in dependencies:
            for h in head:
                flattened_dependencies.append(h)
            for t in token:
                flattened_dependencies.append(t)

        # 去重，去除空白项并保留顺序
        flattened_dependencies = list(dict.fromkeys(flattened_dependencies))
        flattened_dependencies = [re.sub(r'_token', '', keyword) for keyword in flattened_dependencies if keyword]

    return flattened_dependencies


def match_keywords(keywords1, keywords2, threshold=0.8):
    matched_pairs = []
    # 遍历关键词列表中的每个词
    for keyword1 in keywords1:
        #keyword1_doc = nlp(keyword1)        
        for keyword2 in keywords2:
            #keyword2_doc = nlp(keyword2)            
            # 1. 直接匹配
            if keyword1 == keyword2:
                matched_pairs.append((keyword1, keyword2))
                continue
            # 2. 词向量相似度
            # similarity = keyword1_doc.similarity(keyword2_doc)
            # if similarity >= threshold:
            #     matched_pairs.append((keyword1, keyword2))
            #     continue
            # 3. Levenshtein 编辑距离
            edit_distance = levenshtein_distance(keyword1, keyword2)
            max_len = max(len(keyword1), len(keyword2))
            normalized_distance = 1 - (edit_distance / max_len)
            if normalized_distance >= threshold:
                matched_pairs.append((keyword1, keyword2))
    return matched_pairs

####################################################################33
def are_descriptions_similar(desc1, desc2, threshold=0.75):
    """
    使用 SpaCy 判断两段描述是否相似
    :param desc1: 第一段描述
    :param desc2: 第二段描述
    :param threshold: 判断相似度的阀值，默认是0.75
    :return: 返回相似度分数
    """
    if not desc1 or not desc2:
        return 0  # 如果任何描述为空，则认为不相似
    
    # 使用缓存的NLP处理结果
    doc1 = get_nlp_doc(desc1)
    doc2 = get_nlp_doc(desc2)
    
    # 计算相似度
    similarity = doc1.similarity(doc2)
    
    return similarity

# 辅助函数：检查类型是否为 GraphQLNonNull// 仅看当前参数的类型是否为GraphQLNonNull即可。一般先标注是否为GraphQLNonNull，再再
def is_non_null_type(param_type):
    if isinstance(param_type, GraphQLNonNull):
        return True
    # if hasattr(param_type, 'of_type'):
    #     return is_non_null_type(param_type.of_type)
    return False

# 辅助函数：检查类型是否需要解析依赖关系
def should_parse_dependency(param_type, param_name=None):
    base_type = get_base_type(param_type)
    is_id = False
    is_non_null = False
    
    # 判断是否为布尔型或者枚举类型，排除这些类型
    if isinstance(base_type, GraphQLEnumType) or base_type.name == "Boolean":
        return False, is_id
    
    #参数名中包含 'id' 或类型名中包含 'ID'
    if "id" in param_name.lower() or "ID" in base_type.name:
        is_id = True


    # 如果字段为 non_null 
    if is_non_null_type(param_type):
        is_non_null = True
    

    return is_non_null, is_id

def is_not_custom_id_match(param_type, field_type):
    """
    判断参数类型为 ID 时，是否与自定义标量类型匹配
    :param param_name: 参数名（如 "userId"）
    :param param_type: 参数类型（如 "ID"）
    :param field_type: 字段类型（如 "userID"）
    :return: False 如果其中一方为 ID 且另一方为自定义 ID 类型；True 否则
    """
    if param_type == field_type:
        return False

    # 如果两者之一是基础 ID 类型，而另一方是自定义 ID 类型，则不匹配
    
    if param_type == "ID" and re.match(r".*ID$", field_type):
        return False
    if field_type == "ID" and re.match(r".*ID$", param_type):
        return False
    if param_type == field_type:
        return False

    return True

def split_camel_case(name, min_length=2):
    # 使用更灵活的正则表达式来处理命名不规范的情况
    components = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[A-Z][a-z]*[_-][a-z]+', name)
    if len(components) >= min_length:
        return components
    else:
        return []

    
def calculate_similarity(components_str, type_name):
    """
    计算组件列表与对象名之间的相似度得分。

    参数:
    components (list): 要匹配的组件列表。
    type_name (str): 要比较的对象名。

    返回:
    float: 相似度得分。
    """
    
    
    
    # 计算合并后的字符串与 type_name 的 Levenshtein 距离
    distance = levenshtein_distance(components_str, type_name)
    
    # 计算相似度得分，这里简单地使用 1 - (距离 / 最大长度)
    max_length = max(len(components_str), len(type_name))
    similarity_score = 1 - (distance / max_length)
    
    return similarity_score

def get_most_similar_object(components, schema):
    """
    从模式中找到与给定组件列表最相似的对象名，并返回该对象名和其 GraphQL 类型。

    参数:
    components (list): 要匹配的组件列表。
    schema (GraphQLSchema): GraphQL 模式对象。

    返回:
    tuple: 包含最相似对象名和其 GraphQL 类型的元组。
    """
    most_similar_object_name = None
    most_similar_object_type = None
    max_similarity_score = 0


        # 检查 components 列表的最后一个元素是否是 "id"
    if components and components[-1].lower() == "id":
        # 如果是 "id"，则将其从 components 列表中移除
        components = components[:-1]


    # 将 components 合并为一个字符串
    components_str = ''.join(components)

    for type_name, graphql_type in schema.type_map.items():

        if isinstance(graphql_type, GraphQLObjectType) and not isinstance(graphql_type, GraphQLInputObjectType):
            if type_name.startswith("__"):
                continue

            # 过滤根对象如 query 和 mutation
            if type_name in ["Query", "Mutation"]:
                continue

            # 过滤后缀是 edge 的对象
            if type_name.endswith("Edge"):
                continue

            # 过滤一些输出类的对象，如后缀是 payload 或 output
            if type_name.endswith("Payload") or type_name.endswith("Output"):
                continue

            #过滤带errors字段的输出类对象
            id_field = graphql_type.fields.get('errors')
            if id_field:
                #print(type_name)
                continue

            if not any(common_word.lower() in type_name.lower() for common_word in components) and  type_name.lower() not in components_str.lower():
                continue
            

            # 计算相似度得分
            similarity_score = calculate_similarity(components_str.lower(), type_name.lower())
            if similarity_score > max_similarity_score:
                max_similarity_score = similarity_score
                most_similar_object_name = type_name
                most_similar_object_type = graphql_type
                

    
    if most_similar_object_name is None:  # 添加检查
        return None, None
    else:
        #print(components_str, max_similarity_score, most_similar_object_name)
        return most_similar_object_name, most_similar_object_type



def get_most_similar_objects(components, schema):
    """
    从模式中找到与给定组件列表最相似的对象名，并返回该对象名和其 GraphQL 类型。

    参数:
    components (list): 要匹配的组件列表。
    schema (GraphQLSchema): GraphQL 模式对象。

    返回:
    tuple: 包含最相似对象名和其 GraphQL 类型的元组。
    """
    most_similar_object_names = []

    max_similarity_score = 0


        # 检查 components 列表的最后一个元素是否是 "id"
    if components and components[-1].lower() == "id":
        # 如果是 "id"，则将其从 components 列表中移除
        components = components[:-1]


    # 将 components 合并为一个字符串
    components_str = ''.join(components)

    for type_name, graphql_type in schema.type_map.items():

        if isinstance(graphql_type, GraphQLObjectType) and not isinstance(graphql_type, GraphQLInputObjectType):
            if type_name.startswith("__"):
                continue

            # 过滤根对象如 query 和 mutation
            if type_name in ["Query", "Mutation"]:
                continue

            # 过滤后缀是 edge 的对象
            if type_name.endswith("Edge"):
                continue

            # 过滤一些输出类的对象，如后缀是 payload 或 output
            if type_name.endswith("Payload") or type_name.endswith("Output"):
                continue

            #过滤带errors字段的输出类对象
            id_field = graphql_type.fields.get('errors')
            if id_field:
                #print(type_name)
                continue

            if not any(common_word.lower() in type_name.lower() for common_word in components) and  type_name.lower() not in components_str.lower():
                continue
            

            # 计算相似度得分
            similarity_score = calculate_similarity(components_str.lower(), type_name.lower())
            if similarity_score > 0.4:
                most_similar_object_names.append(type_name)
    return most_similar_object_names
               



def remove_common_verbs(words, common_verbs):
    return [word for word in words if word.lower() not in common_verbs]







# 模糊匹配类型和字段名
def match_type_and_field(schema, param_name, param_type, description, operation_name, is_id, is_non_null, arg_key, input_object_name="", prefix=""):
    param_sources = {}
    max_matched_keywords_count = 0  # 用于追踪匹配成功的关键词对的最大数量
    min_levenshtein_distance = float('inf')  # 用于保留字段名和参数名相似度最小的匹配项
    

    # 先提取参数名和参数类型中的关键字
    components_param_name = split_camel_case(param_name)
    components_param_type = split_camel_case(param_type)

    #是否是自定义标量
    if param_type not in ["Int", "Float", "String", "Boolean", "ID"]:
        is_customer_scalar = True

    
    # 提取操作名中的关键字，去除常见动词（如 get, fetch, update 等）
    if input_object_name:
        operation_name_keywords = split_camel_case(input_object_name, min_length=1)[:-1]
    else:
        operation_name_keywords = split_camel_case(operation_name, min_length=1)
    # 提取操作名中的关键字，去除常见动词
    operation_name_keywords = remove_common_verbs(operation_name_keywords, common_verbs)
    operation_name_keywords = list(dict.fromkeys(operation_name_keywords))


    # 提取描述字段中的关键字（如果有）
    description_keywords = []
    if description:
        description_keywords = extract_explicit_dependency2(description)

    # 获取描述中的依赖关系
    dependencies = extract_explicit_dependency(description)

    #首先如果参数名或类型名是复合型


    if components_param_name:
        most_similar_object_name, most_similar_object_type = get_most_similar_object(components_param_name, schema)
        if most_similar_object_name and most_similar_object_type:
            #print(operation_name, param_name, most_similar_object_name)
            param_sources = match_field(components_param_name, most_similar_object_type, param_name, param_type, description, dependencies, most_similar_object_name, is_non_null, is_id, arg_key)
            if param_sources :
                return param_sources
            
    if components_param_type:
        most_similar_object_name, most_similar_object_type = get_most_similar_object(components_param_type, schema)
        if most_similar_object_name and most_similar_object_type:
            #print(operation_name, param_type, most_similar_object_name)
            param_sources = match_field(components_param_name, most_similar_object_type, param_name, param_type, description, dependencies, most_similar_object_name, is_non_null, is_id, arg_key)
            if param_sources :
                return param_sources    
        
    if is_id and "id" not in param_name.lower():
        most_similar_object_name, most_similar_object_type = get_most_similar_object(param_name, schema)
        if most_similar_object_name and most_similar_object_type:
            param_sources = match_field(components_param_name, most_similar_object_type, param_name, param_type, description, dependencies, most_similar_object_name, is_non_null, is_id, arg_key)
            if param_sources :
                return param_sources     
            
        
    # 如果参数名是单一型，参数名没有过多信息，参数类型是否自定义标量, 参数名和类型名以及描述字段综合；；； 如果是id类，参数名不是ID，可以尝试直接匹配对象名。


    most_similar_object_name, most_similar_object_type = get_most_similar_object(operation_name_keywords, schema)
        #print(operation_name, operation_name_keywords, param_name, param_type, most_similar_object_name, description_keywords, input_object_name, prefix)
    if most_similar_object_name and most_similar_object_type:
        
        param_sources = match_field(components_param_name, most_similar_object_type, param_name, param_type, description, dependencies, most_similar_object_name, is_non_null, is_id, arg_key)


    #泛华检索，来处理补充不规范的schema。最后基于描述字段相似性和所有分割关键词，筛选潜在对象，进行字段匹配。寻找依赖对象。忽略类型。

    



    if param_sources:
        return param_sources
    else:
        #print(operation_name, param_name, param_type, most_similar_object_name)
        param_sources = match_field_object(components_param_name, components_param_type, description_keywords, param_name, param_type, description, dependencies, is_non_null, is_id, schema, arg_key)

        if not param_sources:
            param_sources.update({
                arg_key: None
            })

    return param_sources
    



# 匹配字段的辅助函数
def match_field(components, graphql_type, param_name, param_type, description, dependencies, type_name, is_non_null, is_id, arg_key):

    if not components:
        components.append(param_name)
    

    if is_id:
        # 确保 components 中有一个元素是 id
        if 'id' not in components:
            components.append('id')


    param_sources = []
    max_matched_keywords_count = 0
    matched_keywords_count = 0
    min_levenshtein_distance = float('inf')
    core_words_match = []
    core_words_parameter = []
    matched_keywords = []

    if description:
        core_words_parameter = extract_explicit_dependency2(description)

    if is_non_null:
        non_null = 'Ture'
    else:
        non_null = 'False'

    for field_name, field in graphql_type.fields.items():
        field_base_type = get_base_type_name(field.type)

        if param_type == "ID" or re.match(r".*ID$", param_type):
            if is_not_custom_id_match(param_type, field_base_type):
                continue
        else:
            if param_type != field_base_type:
                continue

        if field.description:
            core_words_match = extract_explicit_dependency2(field.description)

        if core_words_parameter and core_words_match:
            matched_keywords = match_keywords(core_words_match, core_words_parameter)
            matched_keywords_count = len(matched_keywords)

        for component in components:
            if is_similar(field_name, component, True):


                levenshtein_dist = levenshtein_distance(field_name, param_name)

                if (matched_keywords_count > max_matched_keywords_count) or (
                    matched_keywords_count == max_matched_keywords_count and levenshtein_dist < min_levenshtein_distance):
                    param_sources = {
                        arg_key: [type_name,field_name]
                    }
                    max_matched_keywords_count = matched_keywords_count
                    min_levenshtein_distance = levenshtein_dist
                elif matched_keywords_count == max_matched_keywords_count and matched_keywords_count == 0:
                    # 在匹配数量为0的情况下，尝试基于编辑距离选择最相似的结果
                    if levenshtein_dist < min_levenshtein_distance:
                        param_sources = {
                            arg_key: [type_name,field_name]
                        }
                        min_levenshtein_distance = levenshtein_dist
    return param_sources


def match_field_object(components_param_name, components_param_type, core_words_parameter, param_name, param_type, description, dependencies, is_non_null, is_id, schema, arg_key):
    
    if not components_param_name:
        components_param_name = param_name.split()
    
    components = list(set(components_param_name + components_param_type + core_words_parameter))
   

    if is_id:
        # 确保 components 中有一个元素是 id
        if 'id' not in components:
            components.append('id')

    param_sources = {}
    max_matched_keywords_count = 0
    matched_keywords_count = 0
    min_levenshtein_distance = float('inf')
    core_words_match = []
    matched_keywords = []

    if is_non_null:
        non_null = 'Ture'
    else:
        non_null = 'False'    

  

    for component in components:
        most_similar_object_names = get_most_similar_objects(component, schema)
        #print (param_name, component, most_similar_object_name)

        for most_similar_object_name in most_similar_object_names:
            most_similar_object_type = schema.type_map.get(most_similar_object_name)
        

            for field_name, field in most_similar_object_type.fields.items():
                combined_name = f"{most_similar_object_name}{field_name}"  

                field_base_type = get_base_type_name(field.type)
            
                # 判断类型匹配逻辑
                is_type_match = False
                if is_id and ("ID" in field_base_type or field_base_type in ["Int", "String"]):
                    is_type_match = True
                else:
                    # 如果不是 ID 类，类型必须完全一致
                    is_type_match = param_type == field_base_type
            
                if not is_type_match:
                    continue 

                if is_id:
                    is_field_similar = is_similar("id", field_name,True)
                else:
                    is_field_similar = is_similar(param_name, field_name,True)

                is_dependency_similar = any(is_similar(dep, combined_name,True) for dep in core_words_parameter)
                description_similarity = are_descriptions_similar(description, field.description)
                current_levenshtein_distance = levenshtein_distance(field_name, param_name)


                if field.description:
                    core_words_match = extract_explicit_dependency2(field.description)  
                if core_words_parameter and core_words_match:
                    matched_keywords = match_keywords(core_words_match, core_words_parameter)
                    matched_keywords_count = len(matched_keywords)

                if (is_field_similar or is_dependency_similar) and description_similarity >= 0.5:
                    #print (param_name, component, most_similar_object_name)
                    #print (core_words_match, matched_keywords)
                    if matched_keywords_count > max_matched_keywords_count and matched_keywords_count > 0:
                        # 发现新的最大匹配对数，清空之前的 param_sources
                        param_sources = {
                            arg_key: [most_similar_object_name,field_name]
                        }
                        max_matched_keywords_count = matched_keywords_count
                        min_levenshtein_distance = current_levenshtein_distance
                    elif matched_keywords_count == max_matched_keywords_count and matched_keywords_count > 0:
                        # 如果匹配对数与当前最大值相同，比较 Levenshtein 距离
                        if current_levenshtein_distance < min_levenshtein_distance:
                            # 如果当前字段名与参数名的相似度更高（距离更小），替换之前的匹配项
                            param_sources = {
                                arg_key: [most_similar_object_name,field_name]
                            }
                            min_levenshtein_distance = current_levenshtein_distance                
    return param_sources


# 递归解析输入对象字段的依赖关系
def match_input_object_fields(schema, input_object_name, description, operation_name, prefix_key= "", visited=None, prefix=""):
    # 初始化 visited 集合用于追踪已经处理的字段
    if visited is None:
        visited = set()

    param_sources = {}
    
    # 如果当前输入对象已经被处理过，避免递归死循环
    if input_object_name in visited:
        return param_sources  # 直接返回空的 param_sources，避免重复处理
    
    # 将当前 input_object_name 标记为已处理
    visited.add(input_object_name)

    input_object_type = schema.type_map.get(input_object_name)
    if isinstance(input_object_type, GraphQLInputObjectType):
        for field_name, field in input_object_type.fields.items():
            field_base_type = get_base_type(field.type)
            field_type_name = get_base_type_name(field.type)
            field_desc = field.description
            full_field_name = f"{prefix}.{field_name}" if prefix else field_name

            field_type = resolve_type(field.type)
            field_key = f"{prefix_key}.{field_name}({field_type})"

            if is_non_null_type(field.type):

                # 如果字段是 GraphQLInputObjectType，则始终递归解析
                if isinstance(field_base_type, GraphQLInputObjectType):
                    # 递归调用时，将结果合并到 param_sources 中                
                    nested_sources = match_input_object_fields(schema, field_type_name, field_desc, operation_name, field_key, visited, full_field_name)
                    param_sources.update(nested_sources)


                else:
                    # 对于非 GraphQLInputObjectType 的字段，使用 should_parse_dependency 进行判断
                    is_non_null ,is_id = should_parse_dependency(field.type, field_name)
                    if is_non_null or is_id:
                        matched_sources = match_type_and_field(schema, field_name, field_type_name, field_desc, operation_name, is_id, is_non_null, field_key, input_object_name, full_field_name)

                        param_sources.update(matched_sources)

    return param_sources

def resolve_type(arg_type):
    if isinstance(arg_type, GraphQLNonNull):
        return f"{resolve_type(arg_type.of_type)}!"
    if isinstance(arg_type, GraphQLList):
        return f"[{resolve_type(arg_type.of_type)}]"
    if isinstance(arg_type, GraphQLEnumType):
        return arg_type.name
    
    return arg_type.name or "Unknown"

# 查找给定操作中的所有参数依赖关系
def get_operation_parameters_sources(schema, operation_name):
    all_param_sources = {}

    operation_types = [schema.query_type]
    if schema.mutation_type:
        operation_types.append(schema.mutation_type)

    for type_name in operation_types:
        graphql_type = type_name

        if hasattr(graphql_type, 'fields'):
            for op_name, operation in graphql_type.fields.items():
                if operation_name and op_name != operation_name:
                    continue
                for arg_name, arg in operation.args.items():
                    # 判断是否需要解析
                    is_non_null ,is_id = should_parse_dependency(arg.type, arg_name)
                    if is_non_null or is_id:
                        param_sources = {}  # 初始化 param_sources 为空
                        param_type = get_base_type(arg.type)
                        param_type_name = get_base_type_name(arg.type)
                        param_desc = arg.description

                        arg_type = resolve_type(arg.type)
                        arg_key = f"{arg_name}({arg_type})" 

                        if isinstance(param_type, GraphQLInputObjectType):
                            param_sources = match_input_object_fields(schema, param_type_name, param_desc, operation_name, arg_key, visited=set())
                        else:
                            param_sources = match_type_and_field(schema, arg_name, param_type_name, param_desc, operation_name, is_id, is_non_null, arg_key)

                        all_param_sources.update(param_sources)

    return all_param_sources


# 查找所有操作中的所有参数依赖关系并保存为 JSON 文件
def save_all_parameters_dependencies_to_json(schema, output_file_path):
    all_operations_sources = {}
    operation_types = [schema.query_type]
    if schema.mutation_type:
        operation_types.append(schema.mutation_type)

    def process_operation(operation_name, graphql_type):

        sources = get_operation_parameters_sources(schema, operation_name)
        all_operations_sources[operation_name] = sources

    with ThreadPoolExecutor() as executor:
        futures = []
        for type_name in operation_types:
            graphql_type = type_name
            if hasattr(graphql_type, 'fields'):
                for operation_name, _ in graphql_type.fields.items():
                    futures.append(executor.submit(process_operation, operation_name, graphql_type))
        for future in futures:
            future.result()

    with open(output_file_path, 'w', encoding='utf-8') as json_file:
        json.dump(all_operations_sources, json_file, indent=2, ensure_ascii=False)
    print(f"Dependencies have been saved to {output_file_path}")



def main():
    # 使用示例
    schema_json = load_schema('introspection_gitlab.json')
    schema = build_graphql_schema(schema_json)
    output_file = 'operation_parameters_dependencies.json'
    save_all_parameters_dependencies_to_json(schema, output_file)

if __name__ == "__main__":
    main()
