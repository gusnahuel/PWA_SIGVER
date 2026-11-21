from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

class PerfilUsuarioView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        personal_id = None
        
        # Verificamos si el usuario tiene un perfil de Personal asociado
        if hasattr(user, 'personal'):
            personal_id = user.personal.id
            
        return Response({
            'id': str(user.id),
            'username': user.username,
            'nombre': user.get_full_name() or user.username,
            'rol': user.rol,
            'personal_id': str(personal_id) if personal_id else None
        })
