from graphql import build_client_schema, GraphQLObjectType, GraphQLUnionType, GraphQLInterfaceType, GraphQLNonNull
from typing import List, Optional
import json

class GraphQLPathFinder:
    def __init__(self, schema):
        """
        初始化 PathFinder，加载 GraphQL Schema。
        :param schema_file: Introspection 查询结果的 JSON 文件路径
        """
        self.schema = schema


    def find_paths_to_object(self, target_object: str, last_field_name = "", max_depth: int = 4) -> List[List[tuple[str, str]]]:
        """
        查找从查询类型和变更类型到目标对象的所有最短路径。
        :param target_object: 目标对象名称
        :param max_depth: 最大搜索深度
        :return: 最短路径列表，每个路径为类型和字段的序列
        """
        type_map = self.schema.type_map
        paths = []  # 最终的路径列表
        shortest_paths: Dict[Tuple[str, str], List[List[Tuple[str, str]]]] = {}  # 保存最短路径

        # 从查询类型和变更类型作为起点
        starting_types = []
        if self.schema.query_type:
            starting_types.append(self.schema.query_type.name)
        if self.schema.mutation_type:
            starting_types.append(self.schema.mutation_type.name)

        for start_type in starting_types:
            stack = [(start_type, [], False)]  # 当前类型和路径栈

            while stack:
                current_type_name, path, is_post_operation = stack.pop()

                # 限制搜索深度
                if len(path) >= max_depth:
                    continue

                graphql_type = type_map.get(current_type_name)
                if not graphql_type:
                    continue

                # 如果类型是联合类型（Union），遍历可能的类型
                if isinstance(graphql_type, GraphQLUnionType):
                    for possible_type in graphql_type.types:
                        if possible_type.name == target_object:
                            if last_field_name:
                                self._update_shortest_paths(shortest_paths, path + [("UNION", current_type_name), (possible_type.name, last_field_name)])
                            else:
                                self._update_shortest_paths(shortest_paths, path + [("UNION", current_type_name), (possible_type.name, None)])
                        elif possible_type.name not in [ptype[0] for ptype in path]:  # 防止循环
                            stack.append((possible_type.name, path + [("UNION", current_type_name)], True))
                    continue

                # 如果类型是接口类型（Interface），遍历其实现类型
                if isinstance(graphql_type, GraphQLInterfaceType):
                    for type_name, possible_type in type_map.items():
                        if isinstance(possible_type, GraphQLObjectType) and graphql_type in possible_type.interfaces:
                            if possible_type.name == target_object:
                                if last_field_name:
                                    self._update_shortest_paths(shortest_paths, path + [("INTERFACE", current_type_name), (possible_type.name, last_field_name)])
                                else:
                                    self._update_shortest_paths(shortest_paths, path + [("INTERFACE", current_type_name), (possible_type.name, None)])
                            elif possible_type.name not in [ptype[0] for ptype in path]:
                                stack.append((possible_type.name, path + [("INTERFACE", current_type_name)], True))
                    continue

                # 如果类型是对象类型，遍历其字段
                if isinstance(graphql_type, GraphQLObjectType):
                    for field_name, field in graphql_type.fields.items():
                        # 如果是操作后再字段 ，跳过非空参数
                        if is_post_operation and any(isinstance(arg.type, GraphQLNonNull) for arg in field.args.values()):
                            continue

                        if len(path) > 0 and 'first' in field.args:
                            # 修改字段名以包含参数
                            field_name_with_first = f"{field_name}(first: 1)"
                        else:
                            field_name_with_first = field_name                        

                        new_path = path + [(current_type_name, field_name_with_first)]
                        field_type_name = self._get_field_base_type(field.type)

                        if field_type_name == target_object:
                            if last_field_name:
                                self._update_shortest_paths(shortest_paths, new_path + [(field_type_name, last_field_name)])
                            else:
                                self._update_shortest_paths(shortest_paths, new_path + [(field_type_name, None)])
                        elif field_type_name not in [ptype[0] for ptype in path]:
                            stack.append((field_type_name, new_path, True))

        # 提取所有的最短路径
        for path_list in shortest_paths.values():
            paths.extend(path_list)

        return paths

    def _update_shortest_paths(self, shortest_paths, new_path: List[tuple[str, str]]):
        """
        更新最短路径字典，保留更短或相等长度的路径。
        :param shortest_paths: 当前保存的最短路径字典
        :param new_path: 新路径
        """
        if not new_path:
            return

        key = new_path[0]  # 使用第一个操作作为 key，比如 ('Query', 'issue')
        current_length = len(new_path)

        if key not in shortest_paths:
            shortest_paths[key] = [new_path]  # 如果 key 不存在，直接添加
        else:
            existing_length = len(shortest_paths[key][0])
            if current_length < existing_length:
                shortest_paths[key] = [new_path]  # 替换为更短的路径
            elif current_length == existing_length:
                shortest_paths[key].append(new_path)  # 如果长度相等，追加路径

    def _get_field_base_type(self, field_type):
        """
        获取字段的基础类型名称。
        :param field_type: 字段的类型对象
        :return: 基础类型名称
        """
        while hasattr(field_type, 'of_type'):
            field_type = field_type.of_type
        return field_type.name

    def format_paths(self, paths: List[List[str]]) -> List[str]:
        """
        格式化路径为字符串形式，处理 UNION 和 INTERFACE 时使用 . 而不是 ->。
        :param paths: 原始路径列表
        :return: 字符串形式的路径列表
        """
        formatted_paths = []
        for path in paths:
            formatted_parts = []
            for ptype, pfield in path:
                if ptype == "UNION" or ptype == "INTERFACE":
                    # 如果是 UNION 或 INTERFACE，则直接用 "."
                    formatted_parts.append(f"{ptype}.{pfield}|")
                    
                elif pfield:
                    # 普通字段用 "->"
                    formatted_parts.append(f"{ptype}.{pfield}>")
                else:
                    # 没有字段名时只添加类型
                    formatted_parts.append(ptype)
            formatted_paths.append("".join(formatted_parts))
        return formatted_paths
    

    def build_field_structure(self, paths: List[str]) -> dict:
        """
        根据路径信息构造 GraphQL 查询中的字段结构。
        :param paths: 路径信息列表，每个路径是以 "Type.field -> Type.field" 格式的字符串。
        :return: 构造的字段结构字典。
        """
        field_structure = {}

        for path in paths:
            fields = path.split(">")
            current_level = field_structure
            last_field_name = fields[-2]

            for field in fields:
                type_name, _, field_name = field.partition('.')

                if type_name == "UNION" or type_name == "INTERFACE":
                    # UNION or INTERFACE 特殊处理
                    _, _, object_name_field = field_name.partition('|')
                    type_name, _, field_name = object_name_field.partition('.')
                    type_name = f"... on {type_name}"
                    
                    if type_name not in current_level:
                        current_level[type_name] = {} 
                    current_level = current_level[type_name]

                    if not field_name:
                        continue
                    else:
                        if field_name not in current_level:
                            current_level[field_name] = {} if field != last_field_name else None
                        current_level = current_level[field_name]

                    
                elif not field_name:  # 如果是最后的 Type
                    continue
                else:
                    if field_name not in current_level:
                        current_level[field_name] = {} if field != last_field_name else None
                    current_level = current_level[field_name]

        return field_structure


    def format_field_structure(self, field_structure: dict, indent: int = 0) -> str:
        """
        将字段结构格式化为非标准 JSON（去掉引号，符合 GraphQL 的查询样式）。
        :param field_structure: 字段结构字典
        :param indent: 当前缩进级别
        :return: 格式化后的字符串
        """
        formatted = []
        indent_str = "  " * indent

        for key, value in field_structure.items():
            # 如果值是字典，递归处理
            if isinstance(value, dict):
                formatted.append(f"{indent_str}{key} {{\n{self.format_field_structure(value, indent + 1)}\n{indent_str}}}")
            else:
                # 如果值不是字典（不常见），直接输出键
                formatted.append(f"{indent_str}{key}")

        return "\n".join(formatted)

    def format_compact_paths(self, paths: List[List[tuple[str, str]]]) -> List[str]:
        """
        将路径格式化为紧凑形式，输出类似于 GraphQL 查询字段的路径（点分隔），移除字段的参数。
        :param paths: 原始路径列表，每个路径是类型和字段的元组列表。
        :return: 格式化后的紧凑路径列表，例如 todo.target.id 或 frecentGroups.issues.nodes.id。
        """
        compact_paths = []
    
        for path in paths:
            compact_parts = []
            for ptype, pfield in path:
                if ptype == "UNION" or ptype == "INTERFACE":
                    # 如果是 UNION 或 INTERFACE，保留字段名，但不输出接口或联合类型的类型名
                    if "|" in pfield:
                        _, field_name = pfield.split('|')
                        compact_parts.append(field_name)
                elif pfield:
                    # 移除字段中的参数（例如从 issues(first: 1) -> issues）
                    if "(" in pfield and ")" in pfield:
                        field_name = pfield.split("(")[0]  # 只取参数前的字段名
                        compact_parts.append(field_name)
                    else:
                        compact_parts.append(pfield)  # 普通字段直接追加字段名
            # 用 "." 拼接路径
            compact_paths.append(".".join(compact_parts))
    
        return compact_paths
    


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GraphQL Path Finder Tool")
    parser.add_argument("-i", "--introspection", required=True, help="Path to the introspection JSON file.")
    parser.add_argument("-o", "--object", required=True, help="The target object name.")
    parser.add_argument("--max-depth", type=int, default=5, help="Maximum search depth (default: 5).")

    args = parser.parse_args()

    with open(args.introspection, 'r', encoding='utf-8') as file:
        introspection_data = json.load(file)
    schema = build_client_schema(introspection_data['data'])

    # 初始化路径查找器
    path_finder = GraphQLPathFinder(schema)

    # 查找路径
    paths = path_finder.find_paths_to_object(args.object, "ID", args.max_depth)

    # 紧凑格式路径
    compact_paths = path_finder.format_compact_paths(paths)
    print("Compact paths:")
    for path in compact_paths:
        print(f"- {path}")

    # 其他格式化方式
    formatted_paths = path_finder.format_paths(paths)
    field_structure = path_finder.build_field_structure(formatted_paths)
    formatted_output = path_finder.format_field_structure(field_structure)

    print("\nField structure:")
    print(formatted_output)
    
    print(f"Found {len(formatted_paths)} path{'s' if len(formatted_paths) != 1 else ''}:")
    for path in formatted_paths:
        print(f"- {path}") 