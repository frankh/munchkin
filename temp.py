import tornado.web
import mimetypes
import os.path

class FileHandler(tornado.web.RequestHandler):
    def get(self, path):
        if not path:
            path = 'index.html'

        if not os.path.exists(path):
            raise tornado.web.HTTPError(404)

        mime_type = mimetypes.guess_type(path)
        self.set_header("Content-Type", mime_type[0] or 'text/plain')

        outfile = open(path, 'rb')
        for line in outfile:
            self.write(line)
        self.finish()
