from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.password_validation import validate_password
from .models import CustomUser

class CustomUserCreationForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['username']
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Enter your username'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove default help texts
        for field_name, field in self.fields.items():
            field.help_text = ''


class MnemonicLoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Enter your username'})
    )
    mnemonic_seed = forms.CharField(
        widget=forms.Textarea(attrs={'placeholder': 'Enter your 12-word mnemonic seed', 'rows': 3})
    )

    def clean(self):
        username = self.cleaned_data.get('username')
        mnemonic_seed = self.cleaned_data.get('mnemonic_seed')

        if username and mnemonic_seed:
            try:
                user = CustomUser.objects.get(username=username)
                # Normalize whitespace in mnemonic (remove extra spaces)
                provided_mnemonic = ' '.join(mnemonic_seed.strip().split())
                stored_mnemonic = ' '.join(user.mnemonic_seed.strip().split())
                
                if provided_mnemonic != stored_mnemonic:
                    raise forms.ValidationError('Invalid mnemonic seed for this username.')
            except CustomUser.DoesNotExist:
                raise forms.ValidationError('Username does not exist.')
        
        return self.cleaned_data