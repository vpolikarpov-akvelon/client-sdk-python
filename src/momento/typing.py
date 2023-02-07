from typing import Iterable, List, Mapping, Set, Union

TCacheName = str

TMomentoValue = Union[str, bytes]

# Scalar Types
TScalarKey = Union[str, bytes]
TScalarValue = TMomentoValue

# Collections
TCollectionName = str
TCollectionValue = Union[str, bytes]

# Dictionary Types
TDictionaryName = TCollectionName
TDictionaryField = Union[str, bytes]
TDictionaryValue = TMomentoValue
TDictionaryFields = Iterable[TDictionaryField]
TDictionaryItems = Union[
    Mapping[TDictionaryField, TDictionaryValue],
    # Mapping[Union[bytes, str], Union[bytes, str]] doesn't accept Mapping[str, str],
    # So we need to add those types here too[]
    Mapping[bytes, bytes],
    Mapping[bytes, str],
    Mapping[str, bytes],
    Mapping[str, str],
]

# List Types
TListName = TCollectionName
TListValue = TMomentoValue
TListValuesInputBytes = Iterable[bytes]
TListValuesInputStr = Iterable[str]
TListValuesInput = Iterable[TListValue]
TListValuesOutputBytes = List[bytes]
TListValuesOutputStr = List[str]
TLIstValuesOutput = Union[TListValuesOutputBytes, TListValuesOutputStr]

# Set Types
TSetName = TCollectionName
TSetElement = TMomentoValue
TSetElementsInputBytes = Iterable[bytes]
TSetElementsInputStr = Iterable[str]
TSetElementsInput = Iterable[TSetElement]
TSetElementsOutputStr = Set[str]
TSetElementsOutputBytes = Set[bytes]
TSetElementsOutput = Union[TSetElementsOutputBytes, TSetElementsOutputStr]
