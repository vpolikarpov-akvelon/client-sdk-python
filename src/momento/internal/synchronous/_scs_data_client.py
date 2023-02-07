from datetime import timedelta
from functools import partial
from typing import Dict, List, Optional

from momento_wire_types.cacheclient_pb2 import (
    Miss,
    _DeleteRequest,
    _DeleteResponse,
    _DictionaryDeleteRequest,
    _DictionaryFetchRequest,
    _DictionaryFieldValuePair,
    _DictionaryGetRequest,
    _DictionaryIncrementRequest,
    _DictionarySetRequest,
    _GetRequest,
    _GetResponse,
    _ListConcatenateBackRequest,
    _ListConcatenateFrontRequest,
    _ListFetchRequest,
    _ListLengthRequest,
    _ListPopBackRequest,
    _ListPopFrontRequest,
    _ListPushBackRequest,
    _ListPushFrontRequest,
    _ListRemoveRequest,
    _SetDifferenceRequest,
    _SetFetchRequest,
    _SetIfNotExistsRequest,
    _SetRequest,
    _SetResponse,
    _SetUnionRequest,
)
from momento_wire_types.cacheclient_pb2_grpc import ScsStub

from momento import logs
from momento.auth import CredentialProvider
from momento.config import Configuration
from momento.errors import UnknownException, convert_error
from momento.internal._utilities import (
    _as_bytes,
    _gen_dictionary_fields_as_bytes,
    _gen_dictionary_items_as_bytes,
    _gen_list_as_bytes,
    _gen_set_input_as_bytes,
    _validate_cache_name,
    _validate_dictionary_name,
    _validate_list_name,
    _validate_set_name,
    _validate_ttl,
)
from momento.internal.common._data_client_ops import (
    get_default_client_deadline,
    wrap_with_error_handling,
)
from momento.internal.common._data_client_scalar_ops import (
    construct_delete_response,
    construct_get_response,
    construct_set_response,
    prepare_delete_request,
    prepare_get_request,
    prepare_set_request,
)
from momento.internal.synchronous._scs_grpc_manager import _DataGrpcManager
from momento.internal.synchronous._utilities import make_metadata
from momento.requests import CollectionTtl
from momento.responses import (
    CacheDelete,
    CacheDeleteResponse,
    CacheDictionaryFetch,
    CacheDictionaryFetchResponse,
    CacheDictionaryGetField,
    CacheDictionaryGetFieldResponse,
    CacheDictionaryGetFields,
    CacheDictionaryGetFieldsResponse,
    CacheDictionaryIncrement,
    CacheDictionaryIncrementResponse,
    CacheDictionaryRemoveFields,
    CacheDictionaryRemoveFieldsResponse,
    CacheDictionarySetFields,
    CacheDictionarySetFieldsResponse,
    CacheGet,
    CacheGetResponse,
    CacheListConcatenateBack,
    CacheListConcatenateBackResponse,
    CacheListConcatenateFront,
    CacheListConcatenateFrontResponse,
    CacheListFetch,
    CacheListFetchResponse,
    CacheListLength,
    CacheListLengthResponse,
    CacheListPopBack,
    CacheListPopBackResponse,
    CacheListPopFront,
    CacheListPopFrontResponse,
    CacheListPushBack,
    CacheListPushBackResponse,
    CacheListPushFront,
    CacheListPushFrontResponse,
    CacheListRemoveValue,
    CacheListRemoveValueResponse,
    CacheSet,
    CacheSetAddElements,
    CacheSetAddElementsResponse,
    CacheSetFetch,
    CacheSetFetchResponse,
    CacheSetIfNotExists,
    CacheSetIfNotExistsResponse,
    CacheSetRemoveElements,
    CacheSetRemoveElementsResponse,
    CacheSetResponse,
)
from momento.typing import (
    TCacheName,
    TDictionaryField,
    TDictionaryFields,
    TDictionaryItems,
    TDictionaryName,
    TListName,
    TListValue,
    TListValuesInput,
    TScalarKey,
    TScalarValue,
    TSetElementsInput,
    TSetName,
)


class _ScsDataClient:
    """Internal"""

    __UNSUPPORTED_LIST_NAME_TYPE_MSG = "Unsupported type for list_name: "
    __UNSUPPORTED_LIST_VALUE_TYPE_MSG = "Unsupported type for value: "
    __UNSUPPORTED_LIST_VALUES_TYPE_MSG = "Unsupported type for values: "
    __UNSUPPORTED_SET_NAME_TYPE_MSG = "Unsupported type for set_name: "
    __UNSUPPORTED_SET_ELEMENTS_TYPE_MSG = "Unsupported tyoe for elements: "

    __UNSUPPORTED_DICTIONARY_NAME_TYPE_MSG = "Unsupported type for dictionary_name: "
    __UNSUPPORTED_DICTIONARY_FIELD_TYPE_MSG = "Unsupported type for field: "
    __UNSUPPORTED_DICTIONARY_FIELDS_TYPE_MSG = "Unsupported type for fields: "
    __UNSUPPORTED_DICTIONARY_ITEMS_TYPE_MSG = "Unsupported type for items: "

    def __init__(self, configuration: Configuration, credential_provider: CredentialProvider, default_ttl: timedelta):
        endpoint = credential_provider.cache_endpoint
        self._logger = logs.logger
        self._logger.debug("Simple cache data client instantiated with endpoint: %s", endpoint)
        self._endpoint = endpoint

        default_deadline: timedelta = get_default_client_deadline(configuration)
        self._default_deadline_seconds = int(default_deadline.total_seconds())

        self._grpc_manager = _DataGrpcManager(credential_provider)

        _validate_ttl(default_ttl)
        self._default_ttl = default_ttl

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def set(
        self,
        cache_name: str,
        key: TScalarKey,
        value: TScalarValue,
        ttl: Optional[timedelta],
    ) -> CacheSetResponse:
        metadata = make_metadata(cache_name)

        def execute_set_request_fn(req: _SetRequest) -> _SetResponse:
            return self._build_stub().Set(
                req,
                metadata=metadata,
                timeout=self._default_deadline_seconds,
            )

        return wrap_with_error_handling(
            cache_name=cache_name,
            request_type="Set",
            prepare_request_fn=partial(
                prepare_set_request,
                key=key,
                value=value,
                ttl=ttl,
                default_ttl=self._default_ttl,
            ),
            execute_request_fn=execute_set_request_fn,
            response_fn=construct_set_response,
            error_fn=CacheSet.Error.from_sdkexception,
            metadata=metadata,
        )

    def set_if_not_exists(
        self, cache_name: TCacheName, key: TScalarKey, value: TScalarValue, ttl: Optional[timedelta]
    ) -> CacheSetIfNotExistsResponse:
        try:
            self._log_issuing_request("SetIfNotExists", {"key": str(key)})

            _validate_cache_name(cache_name)
            item_ttl = self._default_ttl if ttl is None else ttl
            _validate_ttl(item_ttl)
            request = _SetIfNotExistsRequest()
            request.cache_key = _as_bytes(key, "Unsupported type for key: ")
            request.cache_body = _as_bytes(value, "Unsupported type for value: ")
            request.ttl_milliseconds = int(item_ttl.total_seconds() * 1000)

            response = self._build_stub().SetIfNotExists(
                request, metadata=make_metadata(cache_name), timeout=self._default_deadline_seconds
            )

            self._log_received_response("SetIfNotExists", {"key": str(key)})

            result = response.WhichOneof("result")
            if result == "stored":
                return CacheSetIfNotExists.Stored()
            elif result == "not_stored":
                return CacheSetIfNotExists.NotStored()
            else:
                raise UnknownException("SetIfNotExists responded with an unknown result")
        except Exception as e:
            self._log_request_error("set_if_not_exists", e)
            return CacheSetIfNotExists.Error(convert_error(e))

    def get(self, cache_name: str, key: TScalarKey) -> CacheGetResponse:
        metadata = make_metadata(cache_name)

        def execute_get_request_fn(req: _GetRequest) -> _GetResponse:
            return self._build_stub().Get(
                req,
                metadata=metadata,
                timeout=self._default_deadline_seconds,
            )

        return wrap_with_error_handling(
            cache_name=cache_name,
            request_type="Get",
            prepare_request_fn=partial(prepare_get_request, key=key),
            execute_request_fn=execute_get_request_fn,
            response_fn=construct_get_response,
            error_fn=CacheGet.Error.from_sdkexception,
            metadata=metadata,
        )

    def delete(self, cache_name: str, key: TScalarKey) -> CacheDeleteResponse:
        metadata = make_metadata(cache_name)

        def execute_delete_request_fn(req: _DeleteRequest) -> _DeleteResponse:
            return self._build_stub().Delete(
                req,
                metadata=metadata,
                timeout=self._default_deadline_seconds,
            )

        return wrap_with_error_handling(
            cache_name=cache_name,
            request_type="Delete",
            prepare_request_fn=partial(prepare_delete_request, key=key),
            execute_request_fn=execute_delete_request_fn,
            response_fn=construct_delete_response,
            error_fn=CacheDelete.Error.from_sdkexception,
            metadata=metadata,
        )

    # DICTIONARY COLLECTION METHODS
    def dictionary_get_fields(
        self,
        cache_name: TCacheName,
        dictionary_name: TDictionaryName,
        fields: TDictionaryFields,
    ) -> CacheDictionaryGetFieldsResponse:
        try:
            self._log_issuing_request("DictionaryGet", {"dictionary_name": dictionary_name})
            _validate_cache_name(cache_name)
            _validate_dictionary_name(dictionary_name)

            request = _DictionaryGetRequest()
            request.dictionary_name = _as_bytes(dictionary_name, self.__UNSUPPORTED_DICTIONARY_NAME_TYPE_MSG)
            bytes_fields = list(_gen_dictionary_fields_as_bytes(fields, self.__UNSUPPORTED_DICTIONARY_FIELDS_TYPE_MSG))

            request.fields.extend(bytes_fields)

            response = self._build_stub().DictionaryGet(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("DictionaryGet", {"dictionary_name": dictionary_name})

            type = response.WhichOneof("dictionary")
            if type == "found":
                get_responses: List[CacheDictionaryGetFieldResponse] = []
                for field, get_response in zip(bytes_fields, response.found.items):
                    if get_response.result == Miss:
                        get_responses.append(CacheDictionaryGetField.Miss())
                    else:
                        get_responses.append(CacheDictionaryGetField.Hit(get_response.cache_body, field))
                return CacheDictionaryGetFields.Hit(get_responses)
            elif type == "missing":
                return CacheDictionaryGetFields.Miss()
            else:
                raise UnknownException("Unknown dictionary field")
        except Exception as e:
            self._log_request_error("dictionary_get_fields", e)
            return CacheDictionaryGetFields.Error(convert_error(e))

    def dictionary_fetch(
        self, cache_name: TCacheName, dictionary_name: TDictionaryName
    ) -> CacheDictionaryFetchResponse:
        try:
            self._log_issuing_request("DictionaryFetch", {"dictionary_name": dictionary_name})
            _validate_cache_name(cache_name)
            _validate_dictionary_name(dictionary_name)
            request = _DictionaryFetchRequest()
            request.dictionary_name = _as_bytes(dictionary_name, self.__UNSUPPORTED_DICTIONARY_NAME_TYPE_MSG)
            response = self._build_stub().DictionaryFetch(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("DictionaryFetch", {"dictionary_name": dictionary_name})

            type = response.WhichOneof("dictionary")
            if type == "missing":
                return CacheDictionaryFetch.Miss()
            elif type == "found":
                return CacheDictionaryFetch.Hit({item.field: item.value for item in response.found.items})
            else:
                raise UnknownException("Unknown dictionary field")
        except Exception as e:
            self._log_request_error("dictionary_fetch", e)
            return CacheDictionaryFetch.Error(convert_error(e))

    def dictionary_increment(
        self,
        cache_name: TCacheName,
        dictionary_name: TDictionaryName,
        field: TDictionaryField,
        amount: int = 1,
        ttl: CollectionTtl = CollectionTtl.from_cache_ttl(),
    ) -> CacheDictionaryIncrementResponse:
        try:
            self._log_issuing_request("DictionaryIncrement", {"dictionary_name": dictionary_name})
            _validate_cache_name(cache_name)
            _validate_dictionary_name(dictionary_name)

            request = _DictionaryIncrementRequest()
            request.dictionary_name = _as_bytes(dictionary_name, self.__UNSUPPORTED_DICTIONARY_NAME_TYPE_MSG)
            request.field = _as_bytes(field, self.__UNSUPPORTED_DICTIONARY_FIELD_TYPE_MSG)
            request.amount = amount
            request.ttl_milliseconds = self.collection_ttl_or_default_milliseconds(ttl)
            request.refresh_ttl = ttl.refresh_ttl

            response = self._build_stub().DictionaryIncrement(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("DictionaryIncrement", {"dictionary_name": dictionary_name})
            return CacheDictionaryIncrement.Success(response.value)
        except Exception as e:
            self._log_request_error("dictionary_increment", e)
            return CacheDictionaryIncrement.Error(convert_error(e))

    def dictionary_remove_fields(
        self,
        cache_name: TCacheName,
        dictionary_name: TDictionaryName,
        fields: TDictionaryFields,
    ) -> CacheDictionaryRemoveFieldsResponse:
        try:
            self._log_issuing_request("DictionaryDelete", {"dictionary_name": dictionary_name})
            _validate_cache_name(cache_name)
            _validate_dictionary_name(dictionary_name)

            request = _DictionaryDeleteRequest()
            request.dictionary_name = _as_bytes(dictionary_name, self.__UNSUPPORTED_DICTIONARY_NAME_TYPE_MSG)
            request.some.fields.extend(
                _gen_dictionary_fields_as_bytes(fields, self.__UNSUPPORTED_DICTIONARY_FIELDS_TYPE_MSG)
            )

            self._build_stub().DictionaryDelete(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("DictionaryDelete", {"dictionary_name": dictionary_name})
            return CacheDictionaryRemoveFields.Success()
        except Exception as e:
            self._log_request_error("dictionary_remove_fields", e)
            return CacheDictionaryRemoveFields.Error(convert_error(e))

    def dictionary_set_fields(
        self,
        cache_name: TCacheName,
        dictionary_name: TDictionaryName,
        items: TDictionaryItems,
        ttl: CollectionTtl = CollectionTtl.from_cache_ttl(),
    ) -> CacheDictionarySetFieldsResponse:
        try:
            self._log_issuing_request("DictionarySet", {"dictionary_name": dictionary_name})
            _validate_cache_name(cache_name)
            _validate_dictionary_name(dictionary_name)

            request = _DictionarySetRequest()
            request.dictionary_name = _as_bytes(dictionary_name, self.__UNSUPPORTED_DICTIONARY_NAME_TYPE_MSG)
            for field, value in _gen_dictionary_items_as_bytes(items, self.__UNSUPPORTED_DICTIONARY_ITEMS_TYPE_MSG):
                field_value_pair = _DictionaryFieldValuePair()
                field_value_pair.field = field
                field_value_pair.value = value
                request.items.append(field_value_pair)
            request.ttl_milliseconds = self.collection_ttl_or_default_milliseconds(ttl)
            request.refresh_ttl = ttl.refresh_ttl

            self._build_stub().DictionarySet(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("DictionarySet", {"dictionary_name": dictionary_name})
            return CacheDictionarySetFields.Success()
        except Exception as e:
            self._log_request_error("dictionary_set_fields", e)
            return CacheDictionarySetFields.Error(convert_error(e))

    # LIST COLLECTION METHODS
    def list_concatenate_back(
        self,
        cache_name: TCacheName,
        list_name: TListName,
        values: TListValuesInput,
        ttl: CollectionTtl = CollectionTtl.from_cache_ttl(),
        truncate_front_to_size: Optional[int] = None,
    ) -> CacheListConcatenateBackResponse:
        try:
            self._log_issuing_request("ListConcatenateBack", {})
            _validate_cache_name(cache_name)
            _validate_list_name(list_name)

            request = _ListConcatenateBackRequest()
            request.list_name = _as_bytes(list_name, self.__UNSUPPORTED_LIST_NAME_TYPE_MSG)
            request.values.extend(_gen_list_as_bytes(values, self.__UNSUPPORTED_LIST_VALUES_TYPE_MSG))
            request.ttl_milliseconds = self.collection_ttl_or_default_milliseconds(ttl)
            request.refresh_ttl = ttl.refresh_ttl
            if truncate_front_to_size is not None:
                request.truncate_front_to_size = truncate_front_to_size

            response = self._build_stub().ListConcatenateBack(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("ListConcatenateBack", {"list_name": str(request.list_name)})
            return CacheListConcatenateBack.Success(response.list_length)
        except Exception as e:
            self._log_request_error("list_concatenate_back", e)
            return CacheListConcatenateBack.Error(convert_error(e))

    def list_concatenate_front(
        self,
        cache_name: TCacheName,
        list_name: TListName,
        values: TListValuesInput,
        ttl: CollectionTtl = CollectionTtl.from_cache_ttl(),
        truncate_back_to_size: Optional[int] = None,
    ) -> CacheListConcatenateFrontResponse:
        try:
            self._log_issuing_request("ListConcatenateFront", {})
            _validate_cache_name(cache_name)
            _validate_list_name(list_name)

            request = _ListConcatenateFrontRequest()
            request.list_name = _as_bytes(list_name, self.__UNSUPPORTED_LIST_NAME_TYPE_MSG)
            request.values.extend(_gen_list_as_bytes(values, self.__UNSUPPORTED_LIST_VALUES_TYPE_MSG))
            request.ttl_milliseconds = self.collection_ttl_or_default_milliseconds(ttl)
            request.refresh_ttl = ttl.refresh_ttl
            if truncate_back_to_size is not None:
                request.truncate_back_to_size = truncate_back_to_size

            response = self._build_stub().ListConcatenateFront(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("ListConcatenateFront", {"list_name": str(request.list_name)})
            return CacheListConcatenateFront.Success(response.list_length)
        except Exception as e:
            self._log_request_error("list_concatenate_front", e)
            return CacheListConcatenateFront.Error(convert_error(e))

    def list_fetch(self, cache_name: TCacheName, list_name: TListName) -> CacheListFetchResponse:
        try:
            self._log_issuing_request("ListFetch", {"list_name": str(list_name)})
            _validate_cache_name(cache_name)
            _validate_list_name(list_name)
            request = _ListFetchRequest()
            request.list_name = _as_bytes(list_name, self.__UNSUPPORTED_LIST_NAME_TYPE_MSG)
            response = self._build_stub().ListFetch(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("ListFetch", {"list_name": str(request.list_name)})

            type = response.WhichOneof("list")
            if type == "missing":
                return CacheListFetch.Miss()
            elif type == "found":
                return CacheListFetch.Hit(response.found.values)
            else:
                raise UnknownException("Unknown list field")
        except Exception as e:
            self._log_request_error("list_fetch", e)
            return CacheListFetch.Error(convert_error(e))

    def list_length(self, cache_name: TCacheName, list_name: TListName) -> CacheListLengthResponse:
        try:
            self._log_issuing_request("ListLength", {"list_name": str(list_name)})
            _validate_cache_name(cache_name)
            _validate_list_name(list_name)
            request = _ListLengthRequest()
            request.list_name = _as_bytes(list_name, self.__UNSUPPORTED_LIST_NAME_TYPE_MSG)
            response = self._build_stub().ListLength(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("ListLength", {"list_name": str(request.list_name)})

            type = response.WhichOneof("list")
            if type == "missing":
                return CacheListLength.Miss()
            elif type == "found":
                return CacheListLength.Hit(response.found.length)
            else:
                raise UnknownException("Unknown list field")
        except Exception as e:
            self._log_request_error("list_length", e)
            return CacheListLength.Error(convert_error(e))

    def list_pop_back(self, cache_name: TCacheName, list_name: TListName) -> CacheListPopBackResponse:
        try:
            self._log_issuing_request("ListPopBack", {"list_name": str(list_name)})
            _validate_cache_name(cache_name)
            _validate_list_name(list_name)
            request = _ListPopBackRequest()
            request.list_name = _as_bytes(list_name, self.__UNSUPPORTED_LIST_NAME_TYPE_MSG)
            response = self._build_stub().ListPopBack(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("ListPopBack", {"list_name": str(request.list_name)})

            type = response.WhichOneof("list")
            if type == "missing":
                return CacheListPopBack.Miss()
            elif type == "found":
                return CacheListPopBack.Hit(response.found.back)
            else:
                raise UnknownException("Unknown list field")
        except Exception as e:
            self._log_request_error("list_pop_back", e)
            return CacheListPopBack.Error(convert_error(e))

    def list_pop_front(self, cache_name: TCacheName, list_name: TListName) -> CacheListPopFrontResponse:
        try:
            self._log_issuing_request("ListPopFront", {"list_name": str(list_name)})
            _validate_cache_name(cache_name)
            _validate_list_name(list_name)
            request = _ListPopFrontRequest()
            request.list_name = _as_bytes(list_name, self.__UNSUPPORTED_LIST_NAME_TYPE_MSG)
            response = self._build_stub().ListPopFront(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("ListPopFront", {"list_name": str(request.list_name)})

            type = response.WhichOneof("list")
            if type == "missing":
                return CacheListPopFront.Miss()
            elif type == "found":
                return CacheListPopFront.Hit(response.found.front)
            else:
                raise UnknownException("Unknown list field")
        except Exception as e:
            self._log_request_error("list_pop_front", e)
            return CacheListPopFront.Error(convert_error(e))

    def list_push_back(
        self,
        cache_name: TCacheName,
        list_name: TListName,
        value: TListValue,
        ttl: CollectionTtl = CollectionTtl.from_cache_ttl(),
        truncate_front_to_size: Optional[int] = None,
    ) -> CacheListPushBackResponse:
        try:
            self._log_issuing_request("ListPushBack", {})
            _validate_cache_name(cache_name)
            _validate_list_name(list_name)

            request = _ListPushBackRequest()
            request.list_name = _as_bytes(list_name, self.__UNSUPPORTED_LIST_NAME_TYPE_MSG)
            request.value = _as_bytes(value, self.__UNSUPPORTED_LIST_VALUE_TYPE_MSG)
            request.ttl_milliseconds = self.collection_ttl_or_default_milliseconds(ttl)
            request.refresh_ttl = ttl.refresh_ttl
            if truncate_front_to_size is not None:
                request.truncate_front_to_size = truncate_front_to_size

            response = self._build_stub().ListPushBack(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("ListPushBack", {"list_name": str(request.list_name)})
            return CacheListPushBack.Success(response.list_length)
        except Exception as e:
            self._log_request_error("list_push_back", e)
            return CacheListPushBack.Error(convert_error(e))

    def list_push_front(
        self,
        cache_name: TCacheName,
        list_name: TListName,
        value: TListValue,
        ttl: CollectionTtl = CollectionTtl.from_cache_ttl(),
        truncate_back_to_size: Optional[int] = None,
    ) -> CacheListPushFrontResponse:
        try:
            self._log_issuing_request("ListPushFront", {})
            _validate_cache_name(cache_name)
            _validate_list_name(list_name)

            request = _ListPushFrontRequest()
            request.list_name = _as_bytes(list_name, self.__UNSUPPORTED_LIST_NAME_TYPE_MSG)
            request.value = _as_bytes(value, self.__UNSUPPORTED_LIST_VALUE_TYPE_MSG)
            request.ttl_milliseconds = self.collection_ttl_or_default_milliseconds(ttl)
            request.refresh_ttl = ttl.refresh_ttl
            if truncate_back_to_size is not None:
                request.truncate_back_to_size = truncate_back_to_size

            response = self._build_stub().ListPushFront(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("ListPushFront", {"list_name": str(request.list_name)})
            return CacheListPushFront.Success(response.list_length)
        except Exception as e:
            self._log_request_error("list_push_front", e)
            return CacheListPushFront.Error(convert_error(e))

    def list_remove_value(
        self,
        cache_name: TCacheName,
        list_name: TListName,
        value: TListValue,
    ) -> CacheListRemoveValueResponse:
        try:
            self._log_issuing_request("ListRemoveValue", {})
            _validate_cache_name(cache_name)
            _validate_list_name(list_name)

            request = _ListRemoveRequest()
            request.list_name = _as_bytes(list_name, self.__UNSUPPORTED_LIST_NAME_TYPE_MSG)
            request.all_elements_with_value = _as_bytes(value, self.__UNSUPPORTED_LIST_VALUE_TYPE_MSG)

            self._build_stub().ListRemove(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("ListRemoveValue", {"list_name": str(request.list_name)})
            return CacheListRemoveValue.Success()
        except Exception as e:
            self._log_request_error("list_remove_value", e)
            return CacheListRemoveValue.Error(convert_error(e))

    # SET COLLECTION METHODS
    def set_add_elements(
        self,
        cache_name: TCacheName,
        set_name: TSetName,
        elements: TSetElementsInput,
        ttl: CollectionTtl = CollectionTtl.from_cache_ttl(),
    ) -> CacheSetAddElementsResponse:
        try:
            self._log_issuing_request("SetAddElements", {})
            _validate_cache_name(cache_name)
            _validate_set_name(set_name)

            item_ttl = self._default_ttl if ttl.ttl is None else ttl.ttl
            request = _SetUnionRequest()
            request.set_name = _as_bytes(set_name, self.__UNSUPPORTED_SET_NAME_TYPE_MSG)
            request.elements.extend(_gen_set_input_as_bytes(elements, self.__UNSUPPORTED_SET_ELEMENTS_TYPE_MSG))
            request.ttl_milliseconds = int(item_ttl.total_seconds() * 1000)
            request.refresh_ttl = ttl.refresh_ttl

            self._build_stub().SetUnion(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("SetAddElements", {"set_name": str(request.set_name)})
            return CacheSetAddElements.Success()
        except Exception as e:
            self._log_request_error("set_remove_elements", e)
            return CacheSetAddElements.Error(convert_error(e))

    def set_fetch(
        self,
        cache_name: TCacheName,
        set_name: TSetName,
    ) -> CacheSetFetchResponse:
        try:
            self._log_issuing_request("SetFetch", {"set_name": str(set_name)})
            _validate_cache_name(cache_name)
            _validate_set_name(set_name)

            request = _SetFetchRequest()
            request.set_name = _as_bytes(set_name, "Unsupported type for set_name: ")
            response = self._build_stub().SetFetch(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("SetFetch", {"set_name": str(request.set_name)})

            type = response.WhichOneof("set")
            if type == "missing":
                return CacheSetFetch.Miss()
            elif type == "found":
                return CacheSetFetch.Hit(set(response.found.elements))
            else:
                raise UnknownException(f"Unknown set field in response: {type}")
        except Exception as e:
            self._log_request_error("set_fetch", e)
            return CacheSetFetch.Error(convert_error(e))

    def set_remove_elements(
        self, cache_name: TCacheName, set_name: TSetName, elements: TSetElementsInput
    ) -> CacheSetRemoveElementsResponse:
        try:
            self._log_issuing_request("SetRemoveElements", {})
            _validate_cache_name(cache_name)
            _validate_set_name(set_name)

            request = _SetDifferenceRequest()
            request.set_name = _as_bytes(set_name, self.__UNSUPPORTED_SET_NAME_TYPE_MSG)
            request.subtrahend.set.elements.extend(
                _gen_set_input_as_bytes(elements, self.__UNSUPPORTED_SET_ELEMENTS_TYPE_MSG)
            )

            self._build_stub().SetDifference(
                request,
                metadata=make_metadata(cache_name),
                timeout=self._default_deadline_seconds,
            )
            self._log_received_response("SetRemoveElements", {"set_name": str(request.set_name)})
            return CacheSetRemoveElements.Success()
        except Exception as e:
            self._log_request_error("set_remove_elements", e)
            return CacheSetRemoveElements.Error(convert_error(e))

    def _log_received_response(self, request_type: str, request_args: Dict[str, str]) -> None:
        self._logger.log(logs.TRACE, f"Received a {request_type} response for {request_args}")

    def _log_issuing_request(self, request_type: str, request_args: Dict[str, str]) -> None:
        self._logger.log(logs.TRACE, f"Issuing a {request_type} request with {request_args}")

    def _log_request_error(self, request_type: str, e: Exception) -> None:
        self._logger.warning(f"{request_type} failed with exception: {e}")

    def collection_ttl_or_default_milliseconds(self, collection_ttl: CollectionTtl) -> int:
        return self.ttl_or_default_milliseconds(collection_ttl.ttl)

    def ttl_or_default_milliseconds(self, ttl: Optional[timedelta]) -> int:
        which_ttl = self._default_ttl
        if ttl is not None:
            which_ttl = ttl

        return int(which_ttl.total_seconds() * 1000)

    def _build_stub(self) -> ScsStub:
        return self._grpc_manager.stub()

    def close(self) -> None:
        self._grpc_manager.close()
