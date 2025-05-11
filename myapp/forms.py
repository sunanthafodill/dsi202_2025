from django import forms
from .models import Store
from django.core.files.storage import default_storage

class StoreAdminForm(forms.ModelForm):
    additional_images_upload = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'multiple': True}),
        required=False,
        label="Additional Images",
        help_text="Select multiple image files for the store (similar to store image)"
    )

    class Meta:
        model = Store
        fields = '__all__'

    def clean_additional_images_upload(self):
        files = self.files.getlist('additional_images_upload')
        image_paths = []
        for file in files:
            if not file.content_type.startswith('image/'):
                raise forms.ValidationError(f"File {file.name} is not an image")
            path = default_storage.save(f"store_images/{file.name}", file)
            image_paths.append(f"/media/{path}")
        return image_paths

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('additional_images_upload'):
            current_images = instance.additional_images or []
            new_images = self.cleaned_data['additional_images_upload']
            instance.additional_images = current_images + new_images
        if commit:
            instance.save()
        return instance