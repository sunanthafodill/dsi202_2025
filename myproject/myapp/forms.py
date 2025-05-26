from django import forms
from .models import Store, Address, Allergy, Profile

class StoreAdminForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = '__all__'

    def clean_additional_images(self):
        images = self.cleaned_data.get('additional_images')
        if not isinstance(images, list):
            raise forms.ValidationError("รูปภาพเพิ่มเติมต้องเป็นรายการ")
        for img in images:
            if len(img) > 200:
                raise forms.ValidationError("URL รูปภาพต้องไม่ยาวเกิน 200 ตัวอักษร")
        return images

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['label', 'address_line', 'subdistrict', 'district', 'province', 'postal_code', 'phone_number', 'is_default']

class AllergyForm(forms.ModelForm):
    class Meta:
        model = Allergy
        fields = ['name']

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['phone_number']