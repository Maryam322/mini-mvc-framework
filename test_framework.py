import unittest
import json
from core.router import Router
from .core.request import Request
from .core.response import Response
from .models.base import Model
from.models.fields import CharField, IntegerField
from .models.exceptions import ValidationError, ObjectDoesNotExist
from .controllers.model_controller import ModelController
from .controllers.base import Controller

# --- 1. Request/Response Tests ---

class TestRequest(unittest.TestCase):
    def test_request_initialization(self):
        req = Request(method='POST', path='/api/data')
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.path, '/api/data')

    def test_query_params_parsing(self):
        req = Request(path='/search?q=python&page=1')
        self.assertEqual(req.query_params['q'], 'python')
        self.assertEqual(req.query_params['page'], '1')

    def test_json_parsing(self):
        body = json.dumps({'key': 'value'})
        req = Request(method='POST', body=body)
        self.assertEqual(req.json(), {'key': 'value'})

    def test_invalid_json_parsing(self):
        req = Request(method='POST', body='invalid')
        self.assertEqual(req.json(), {})

class TestResponse(unittest.TestCase):
    def test_response_creation(self):
        res = Response(body='ok', status=200)
        self.assertEqual(res.status, 200)
        self.assertEqual(res.body, 'ok')
        self.assertEqual(res.headers['Content-Type'], 'text/plain')

    def test_json_factory(self):
        res = Response.json({'a': 1})
        self.assertEqual(res.status, 200)
        self.assertEqual(json.loads(res.body), {'a': 1})
        self.assertEqual(res.headers['Content-Type'], 'application/json')

    def test_error_factories(self):
        not_found = Response.not_found()
        self.assertEqual(not_found.status, 404)
        
        bad_req = Response.bad_request()
        self.assertEqual(bad_req.status, 400)

class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = Router()

    def test_simple_match(self):
        self.router.get('/hello', lambda r: "world")
        req = Request(path='/hello')
        handler = self.router.match(req)
        self.assertIsNotNone(handler)
        self.assertEqual(handler(req), "world")

    def test_param_match(self):
        self.router.get('/users/<id>', lambda r: f"user {r.path_params['id']}")
        req = Request(path='/users/123')
        handler = self.router.match(req)
        self.assertIsNotNone(handler)
        self.assertEqual(handler(req), "user 123")
        self.assertEqual(req.path_params['id'], '123')

    def test_method_match(self):
        self.router.post('/submit', lambda r: "submitted")
        
        # Wrong method
        req_get = Request(method='GET', path='/submit')
        self.assertIsNone(self.router.match(req_get))

        # Correct method
        req_post = Request(method='POST', path='/submit')
        handler = self.router.match(req_post)
        self.assertIsNotNone(handler)

    def test_no_match(self):
        req = Request(path='/unknown')
        self.assertIsNone(self.router.match(req))

# --- 2. Model Tests ---

class TestUser(Model):
    name = CharField(required=True)
    age = IntegerField()

class TestModel(unittest.TestCase):
    def setUp(self):
        Model._clear_storage()

    def test_create_and_get(self):
        user = TestUser.create(name="Alice", age=25)
        self.assertIsNotNone(user.id)
        
        fetched = TestUser.get(user.id)
        self.assertEqual(fetched.name, "Alice")
        self.assertEqual(fetched.age, 25)

    def test_all_and_count(self):
        TestUser.create(name="A", age=1)
        TestUser.create(name="B", age=2)
        
        self.assertEqual(TestUser.count(), 2)
        self.assertEqual(len(TestUser.all()), 2)

    def test_update(self):
        user = TestUser.create(name="Old", age=20)
        user.name = "New"
        user.save()
        
        fetched = TestUser.get(user.id)
        self.assertEqual(fetched.name, "New")

    def test_validation_constraints(self):
        # Missing required field
        with self.assertRaises(ValidationError):
            TestUser.create(age=20)

    def test_integer_validation(self):
        with self.assertRaises(ValidationError): # IntegerField raises ValidationError for invalid types
            # If IntegerField checks type strictly or casting fails
            # Let's verify IntegerField behavior. If it casts, this might pass depending on impl.
            # Assuming 'abc' fails int casting.
            u = TestUser(name="Test", age="abc") # Constructor likely sets, save validates
            u.save()

# --- 3. Controller Tests ---

class UserController(ModelController):
    model = TestUser

class TestController(unittest.TestCase):
    def setUp(self):
        Model._clear_storage()
        TestUser.create(name="Existing", age=30)

    def test_list(self):
        req = Request()
        ctrl = UserController(req)
        res = ctrl.list()
        self.assertEqual(res.status, 200)
        data = json.loads(res.body)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], "Existing")

    def test_create_success(self):
        body = json.dumps({"name": "NewUser", "age": 22})
        req = Request(method='POST', body=body)
        ctrl = UserController(req)
        res = ctrl.create()
        self.assertEqual(res.status, 201)
        
        self.assertEqual(TestUser.count(), 2)

    def test_create_validation_error(self):
        # Missing name
        body = json.dumps({"age": 22})
        req = Request(method='POST', body=body)
        ctrl = UserController(req)
        res = ctrl.create()
        self.assertEqual(res.status, 400) # Bad Request

    def test_retrieve_found(self):
        user = TestUser.all()[0]
        req = Request()
        ctrl = UserController(req)
        res = ctrl.retrieve(user.id)
        self.assertEqual(res.status, 200)
        self.assertEqual(json.loads(res.body)['name'], "Existing")

    def test_retrieve_not_found(self):
        req = Request()
        ctrl = UserController(req)
        res = ctrl.retrieve(999)
        self.assertEqual(res.status, 404)

# --- 4. Integration Tests ---

class TestIntegration(unittest.TestCase):
    def setUp(self):
        Model._clear_storage()
        self.router = Router()
        
        # Setup route
        def handle_list_users(req):
            return UserController(req).list()
            
        def handle_create_user(req):
            return UserController(req).create()

        self.router.get('/users', handle_list_users)
        self.router.post('/users', handle_create_user)

    def test_full_flow(self):
        # 1. Create a user via valid request
        body = json.dumps({"name": "Integrated", "age": 50})
        req = Request(method='POST', path='/users', body=body)
        
        handler = self.router.match(req)
        res = handler(req)
        
        self.assertEqual(res.status, 201)
        
        # 2. Verify it's in DB
        self.assertEqual(TestUser.count(), 1)
        
        # 3. Fetch list
        req_list = Request(method='GET', path='/users')
        handler_list = self.router.match(req_list)
        res_list = handler_list(req_list)
        
        self.assertEqual(res_list.status, 200)
        data = json.loads(res_list.body)
        self.assertEqual(data[0]['name'], "Integrated")

if __name__ == '__main__':
    unittest.main()

 