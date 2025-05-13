from django import forms
from .models import Store, Address, Allergy, Profile
from django.core.files.storage import default_storage
from django.contrib.auth.models import User

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


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['label', 'subdistrict', 'district', 'province', 'postal_code', 'phone_number']
        labels = {
            'label': 'ชื่อที่อยู่ (เช่น บ้าน, ที่ทำงาน)',
            'subdistrict': 'ตำบล/แขวง',
            'district': 'อำเภอ/เขต',
            'province': 'จังหวัด',
            'postal_code': 'รหัสไปรษณีย์',
            'phone_number': 'เบอร์โทร',
        }

class AllergyForm(forms.ModelForm):
    class Meta:
        model = Allergy
        fields = ['name']
        labels = {
            'name': 'ชื่อสารก่อภูมิแพ้ (เช่น แป้งสาลี, ถั่ว)',
        }

class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, label='ชื่อ')
    last_name = forms.CharField(max_length=30, label='นามสกุล')

    class Meta:
        model = Profile
        fields = ['phone_number']
        labels = {
            'phone_number': 'เบอร์โทร',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
            profile.save()
        return profile