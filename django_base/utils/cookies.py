class set_cookie:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        value = getattr(request, 'cookie_value', None)
        if value == None:
            pass
        else:   
            response.set_cookie('key', value, max_age=3600)  # Expires in 1 hour

        return response
