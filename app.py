from http.server import HTTPServer, BaseHTTPRequestHandler
import inspect
import json

from models.base import Model
from models.fields import CharField, IntegerField, DateTimeField
from core.request import Request
from core.response import Response
from core.router import Router
from controllers.model_controller import ModelController


# ==========================================
# Models
# ==========================================

class User(Model):
    name = CharField(max_length=100, required=True)
    email = CharField(max_length=200, required=True)
    created_at = DateTimeField(auto_now=True)

class Post(Model):
    title = CharField(max_length=200, required=True)
    content = CharField(max_length=5000)
    author_id = IntegerField(required=True)
    created_at = DateTimeField(auto_now=True)

class Comment(Model):
    post_id = IntegerField(required=True)
    content = CharField(max_length=500, required=True)
    author_id = IntegerField(required=True)
    created_at = DateTimeField(auto_now=True)

# ==========================================
# Controllers
# ==========================================

class UserController(ModelController):
    model = User

class PostController(ModelController):
    model = Post

class CommentController(ModelController):
    model = Comment

    def create_for_post(self, id):
        # 'id' here is the post_id from the URL /posts/<id>/comments
        # We need to inject it into the body or just set it
        data = self.request.json()
        data['post_id'] = int(id)
        
        # Simple validation that author_id exists is absent for brevity, 
        # but in real app we'd check User.get(data['author_id'])
        
        try:
            instance = self.model.create(**data)
            return Response.created(instance.to_dict())
        except Exception as e:
            return Response.bad_request(str(e))

    def list_for_post(self, id):
        # List comments for post <id>
        # Naive implementation: get all and filter
        all_comments = self.model.all()
        # Filter
        post_comments = [c for c in all_comments if c.post_id == int(id)]
        return Response.json([c.to_dict() for c in post_comments])


# ==========================================
# App Setup & Routing
# ==========================================

router = Router()

def register_controller(controller_cls, method_name):
    """
    Adapter to bind a controller method to the router handler signature.
    Matches request, instantiates controller, calls method with params.
    """
    def handler(request):
        # Dependency Injection / Factory could go here
        controller = controller_cls(request)
        func = getattr(controller, method_name)
        
        # Inspect signature to pass path parameters
        sig = inspect.signature(func)
        kwargs = {}
        for param in sig.parameters:
            if param in request.path_params:
                kwargs[param] = request.path_params[param]
                
        return func(**kwargs)
    return handler

# User Routes
router.get('/users', register_controller(UserController, 'list'))
router.post('/users', register_controller(UserController, 'create'))
router.get('/users/<id>', register_controller(UserController, 'retrieve'))

# Post Routes
router.get('/posts', register_controller(PostController, 'list'))
router.post('/posts', register_controller(PostController, 'create'))
router.get('/posts/<id>', register_controller(PostController, 'retrieve'))

# Comment Routes
router.post('/posts/<id>/comments', register_controller(CommentController, 'create_for_post'))
router.get('/posts/<id>/comments', register_controller(CommentController, 'list_for_post'))


# ==========================================
# Server Adapter
# ==========================================

class FrameworkHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._handle()
        
    def do_POST(self):
        self._handle()
        
    def do_PUT(self):
        self._handle()
        
    def do_DELETE(self):
        self._handle()

    def _handle(self):
        # Read Body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        # Create Request
        req = Request(
            method=self.command,
            path=self.path,
            body=body,
            headers=self.headers
        )
        
        # Match Route
        handler = router.match(req)
        
        if handler:
            try:
                resp = handler(req)
            except Exception as e:
                resp = Response.json({"error": "Internal Server Error", "details": str(e)}, status=500)
        else:
            resp = Response.not_found()
            
        # Send Response
        self.send_response(resp.status)
        for k, v in resp.headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp.body.encode('utf-8'))

def run_server():
    server_address = ('', 8000)
    print("Starting mini_framework blog app on port 8000...")
    print("Available Routes:")
    for r in router.routes:
        print(f"  {r['method']} {r['regex'].pattern}")
        
    httpd = HTTPServer(server_address, FrameworkHTTPHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

if __name__ == '__main__':
    run_server()
