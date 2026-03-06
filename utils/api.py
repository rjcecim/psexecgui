import ctypes
from ctypes import wintypes
from typing import List, Tuple

# Carregar kernel32.dll
kernel32 = ctypes.windll.kernel32

# Definir tipos de retorno das funções
kernel32.GetActiveProcessorGroupCount.restype = wintypes.WORD
kernel32.GetActiveProcessorCount.restype = wintypes.DWORD

# Definir tipos de argumentos
kernel32.GetActiveProcessorCount.argtypes = [wintypes.WORD]

def get_processor_groups() -> List[int]:
    """
    Obtém a lista de IDs de grupos de processador ativos.
    
    Returns:
        List[int]: Lista de IDs de grupos (0, 1, 2, etc.)
    """
    try:
        group_count = kernel32.GetActiveProcessorGroupCount()
        return list(range(group_count))
    except Exception as e:
        print(f"Erro ao obter grupos de processador: {e}")
        return [0]  # Fallback para grupo 0

def get_processor_count(group_id: int) -> int:
    """
    Obtém o número de CPUs lógicos em um grupo específico.
    
    Args:
        group_id (int): ID do grupo de processador
        
    Returns:
        int: Número de CPUs lógicos no grupo
    """
    try:
        cpu_count = kernel32.GetActiveProcessorCount(group_id)
        return cpu_count
    except Exception as e:
        print(f"Erro ao obter CPUs do grupo {group_id}: {e}")
        return 1  # Fallback para 1 CPU

def get_all_processor_info() -> List[Tuple[int, int]]:
    """
    Obtém informações de todos os grupos de processador.
    
    Returns:
        List[Tuple[int, int]]: Lista de tuplas (group_id, cpu_count)
    """
    groups = get_processor_groups()
    result = []
    
    for group_id in groups:
        cpu_count = get_processor_count(group_id)
        result.append((group_id, cpu_count))
    
    return result

def validate_affinity_mask(affinity_text: str, max_cpu: int) -> bool:
    """
    Valida uma máscara de afinidade de CPU.
    
    Args:
        affinity_text (str): Texto da máscara (ex: "1,2,3")
        max_cpu (int): Número máximo de CPU válido
        
    Returns:
        bool: True se a máscara é válida
    """
    if not affinity_text.strip():
        return True  # Vazio é válido (não especificar afinidade)
    
    try:
        # Dividir por vírgula e converter para inteiros
        cpu_list = [int(x.strip()) for x in affinity_text.split(',') if x.strip()]
        
        # Verificar se todos os valores estão no range válido
        for cpu in cpu_list:
            if cpu < 1 or cpu > max_cpu:
                return False
        
        # Verificar se não há duplicatas
        return len(cpu_list) == len(set(cpu_list))
        
    except ValueError:
        return False

def format_affinity_mask(cpu_list: List[int]) -> str:
    """
    Formata uma lista de CPUs em uma máscara de afinidade.
    
    Args:
        cpu_list (List[int]): Lista de IDs de CPU
        
    Returns:
        str: Máscara formatada (ex: "1,2,3")
    """
    if not cpu_list:
        return ""
    
    return ",".join(map(str, sorted(cpu_list)))

def parse_affinity_mask(affinity_text: str) -> List[int]:
    """
    Converte uma máscara de afinidade em lista de CPUs.
    
    Args:
        affinity_text (str): Máscara de afinidade (ex: "1,2,3")
        
    Returns:
        List[int]: Lista de IDs de CPU
    """
    if not affinity_text.strip():
        return []
    
    try:
        return sorted([int(x.strip()) for x in affinity_text.split(',') if x.strip()])
    except ValueError:
        return [] 