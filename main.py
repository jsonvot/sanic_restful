import copy
import inspect
import types
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Optional, Union, Iterable, List

from sanic import Sanic
from sanic.blueprints import Blueprint
from sanic.constants import HTTPMethod
from sanic.models.handler_types import RouteHandler
from sanic.response import json
from sanic.views import HTTPMethodView


class CreateModelMixin:

    async def create(self, request, *args, **kwargs):
        ...

    async def post(self, request, **kwargs):
        # await self.create(request, *args, **kwargs)
        return json({'code': 0, 'msg': 'create method'})


class ListModelMixin:

    async def list(self, request, *args, **kwargs):
        ...


class UpdateModelMixin:

    async def update(self, request, *args, **kwargs):
        ...

    async def put(self, request, **kwargs):
        # return await self.update(request, *args, **kwargs)
        return json({'code': 0, 'msg': 'put method'})


class PartialUpdateModelMixin:

    async def partial_update(self, request, *args, **kwargs):
        ...

    async def patch(self, request, **kwargs):
        # return await self.partial_update(request, *args, **kwargs)

        return json({'code': 0, 'msg': 'patch method'})


class DestroyModelMixin:

    async def destroy(self, request, *args, **kwargs):
        ...

    async def delete(self, request, **kwargs):
        # return await self.destroy(request, *args, **kwargs)
        return json({'code': 0, 'msg': 'delete method'})


class RetrieveModelMixin:
    async def retrieve(self, request, *args, **kwargs):
        ...


class GenericViewSet(HTTPMethodView):
    async def get(self, request, **kwargs):
        # return await self.retrieve(request, *args, **kwargs)
        if kwargs:
            return json({'code': 0, 'msg': f'retrieve method, {kwargs=}'})
        return json({'code': 0, 'msg': 'list method'})


def clone_class(source_class, target_class):
    """
    :param source_class:
    :param target_class:
    :return:
    """
    assert inspect.isclass(source_class), "source_class must be a class"
    classes = [cls for cls in source_class.mro() if cls is not object]

    for cls in reversed(classes):
        for name, member in cls.__dict__.items():
            if isinstance(member, classmethod):
                unbound = types.FunctionType(
                    member.__func__.__code__,
                    member.__func__.__globals__,
                    name=member.__func__.__name__,
                    argdefs=member.__func__.__defaults__,
                    closure=member.__func__.__closure__
                )
                new_member = types.MethodType(unbound, target_class)
            elif isinstance(member, staticmethod):
                unbound = types.FunctionType(
                    member.__func__.__code__,
                    member.__func__.__globals__,
                    name=member.__func__.__name__,
                    argdefs=member.__func__.__defaults__,
                    closure=member.__func__.__closure__
                )
                new_member = types.MethodType(unbound, target_class)
            elif callable(member):
                unbound = types.FunctionType(
                    member.__code__,
                    member.__globals__,
                    name=member.__name__,
                    argdefs=member.__defaults__,
                    closure=member.__closure__
                )
                new_member = types.MethodType(unbound, target_class)
            elif not name.startswith('__') and not inspect.isbuiltin(member):
                new_member = copy.deepcopy(member)
            else:
                continue
            setattr(target_class, name, new_member)


class RestViewTypeEnum(StrEnum):
    LIST = 'list'
    DETAIL = 'detail'


class RestMethod(StrEnum):
    CREATE = 'create'
    LIST = 'list'
    RETRIEVE = 'retrieve'
    UPDATE = 'update'
    PARTIAL_UPDATE = 'partial_update'
    DESTROY = 'destroy'


RestMethodMap = {
    RestMethod.CREATE: HTTPMethod.POST,
    RestMethod.LIST: HTTPMethod.GET,
    RestMethod.RETRIEVE: HTTPMethod.GET,
    RestMethod.UPDATE: HTTPMethod.PUT,
    RestMethod.PARTIAL_UPDATE: HTTPMethod.PATCH,
    RestMethod.DESTROY: HTTPMethod.DELETE,
}


@dataclass
class RestRoute:
    methods: list
    uri: str = ''


class RestBlueprint(Blueprint):
    rest_route_map = {
        RestViewTypeEnum.LIST: RestRoute(
            methods=[
                RestMethod.LIST,
                RestMethod.CREATE
            ],
        ),
        RestViewTypeEnum.DETAIL: RestRoute(
            methods=[
                RestMethod.RETRIEVE,
                RestMethod.UPDATE,
                RestMethod.PARTIAL_UPDATE,
                RestMethod.DESTROY,
            ]
        )
    }

    @classmethod
    def _get_rest_routes(cls, uri: str) -> dict:
        lstr, rstr, end_char = '/<', '>', '/'
        rest_route_map = copy.deepcopy(cls.rest_route_map)
        if not all([rstr in uri, lstr in uri]):
            rest_route_map[RestViewTypeEnum.LIST].uri = uri
        else:
            idx = uri.rindex(lstr)
            rest_route_map[RestViewTypeEnum.DETAIL].uri = uri
            rest_route_map[RestViewTypeEnum.LIST].uri = uri[:idx] if (idx > 0 and not uri.endswith(end_char)) else \
                uri[:idx + 1]  
        return rest_route_map

    def _add_route(
            self,
            handler: RouteHandler,
            uri: str,
            methods: Iterable[str],
            host: Optional[Union[str, List[str]]] = None,
            strict_slashes: Optional[bool] = None,
            version: Optional[Union[int, str, float]] = None,
            name: Optional[str] = None,
            stream: bool = False,
            version_prefix: str = "/v",
            error_format: Optional[str] = None,
            unquote: bool = False,
            **ctx_kwargs: Any,
    ) -> Optional[RouteHandler]:
        if hasattr(handler, "view_class"):
            allow_methods = [*methods]
            methods = set()

            for method in allow_methods:
                view_class = getattr(handler, "view_class")
                _handler = getattr(view_class, method, None)
                if _handler:
                    methods.add(RestMethodMap[method].value)
                    if hasattr(_handler, "is_stream"):
                        stream = True

            if not methods:
                return

        if strict_slashes is None:
            strict_slashes = self.strict_slashes

        self.route(
            uri=uri,
            methods=methods,
            host=host,
            strict_slashes=strict_slashes,
            stream=stream,
            version=version,
            name=name,
            version_prefix=version_prefix,
            error_format=error_format,
            unquote=unquote,
            **ctx_kwargs,
        )(handler)
        return handler

    def add_resource_route(
            self,
            view,
            uri: str,
            view_name: Optional[str] = None,
            allow_view: RestViewTypeEnum = None,
            **kwargs
    ):
        if uri and not uri.startswith('/'):
            uri = '/' + uri
        view_name = view_name or view.__name__
        class_args = kwargs.pop('class_args', ())
        class_kwargs = kwargs.pop('class_kwargs', {})
        for k, r in self._get_rest_routes(uri).items():
            if not r.uri:
                continue
            if allow_view and k != allow_view:
                continue
            name = f'{view_name}~{k}'
            clone_view = type(name, (object,), {})
            clone_class(view, clone_view)
            handler = getattr(clone_view, 'as_view')(*class_args, **class_kwargs)
            self._add_route(handler, r.uri, methods=r.methods, name=name, **kwargs)


app = Sanic(__name__)
app.config.update(dict(
    OAS_URL_PREFIX='/docs',
    OAS_UI_DEFAULT='swagger',
    SWAGGER_UI_CONFIGURATION={
        "docExpansion": "list"
    },
    OAS_UI_SWAGGER_VERSION='5.0.0',
))


class UserView(
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    PartialUpdateModelMixin,
    DestroyModelMixin,
    GenericViewSet):
    ...


class ClassView(CreateModelMixin,
                ListModelMixin,
                RetrieveModelMixin,
                UpdateModelMixin,
                PartialUpdateModelMixin,
                DestroyModelMixin,
                GenericViewSet):
    ...


class StudentView(CreateModelMixin,
                  ListModelMixin,
                  RetrieveModelMixin,
                  # UpdateModelMixin,
                  # PartialUpdateModelMixin,
                  DestroyModelMixin,
                  GenericViewSet):
    ...


bpa = RestBlueprint('Blueprint_A', url_prefix='/bpa')
bpb = RestBlueprint('Blueprint_B', url_prefix='/bpb')
# bpc = RestBlueprint('Blueprint_C', url_prefix='/bpc')

bpa.add_resource_route(UserView, '/user', view_name='user')
bpb.add_resource_route(ClassView, '/class/<class_id:int>', view_name='class')
bpb.add_resource_route(StudentView, '/student/<student_id:int>', view_name='student')

app.blueprint([bpa, bpb])
