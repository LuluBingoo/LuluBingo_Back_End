from getpass import getpass
import sys

from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError

from accounts.models import ShopUser


class Command(BaseCommand):
    help = "Create the first manager account for the admin portal."

    @staticmethod
    def _is_interactive() -> bool:
        stdin = getattr(sys, "stdin", None)
        return bool(stdin and hasattr(stdin, "isatty") and stdin.isatty())

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, help="Manager username")
        parser.add_argument("--name", type=str, help="Full name")
        parser.add_argument("--email", type=str, help="Contact email")
        parser.add_argument("--phone", type=str, help="Contact phone")
        parser.add_argument("--password", type=str, help="Password")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow creating another manager even if one already exists.",
        )

    def _required_value(self, options, key, prompt, secret=False):
        value = (options.get(key) or "").strip()
        if value:
            return value

        if not self._is_interactive():
            raise CommandError(f"Missing required option --{key} in non-interactive mode.")

        while True:
            typed = getpass(prompt) if secret else input(prompt)
            typed = (typed or "").strip()
            if typed:
                return typed
            self.stderr.write(self.style.ERROR("This field is required."))

    def _password_value(self, options):
        password = (options.get("password") or "").strip()
        if password:
            validate_password(password)
            return password

        if not self._is_interactive():
            raise CommandError("Missing required option --password in non-interactive mode.")

        while True:
            first = getpass("Password: ").strip()
            second = getpass("Confirm password: ").strip()
            if not first:
                self.stderr.write(self.style.ERROR("Password is required."))
                continue
            if first != second:
                self.stderr.write(self.style.ERROR("Passwords do not match. Try again."))
                continue
            validate_password(first)
            return first

    def handle(self, *args, **options):
        existing = ShopUser.objects.filter(role=ShopUser.Role.MANAGER).count()
        if existing > 0 and not options.get("force"):
            raise CommandError(
                "A manager already exists. Use --force to create an additional manager."
            )

        username = self._required_value(options, "username", "Username: ")
        name = self._required_value(options, "name", "Full name: ")
        email = self._required_value(options, "email", "Contact email: ")
        phone = self._required_value(options, "phone", "Contact phone: ")
        password = self._password_value(options)

        if ShopUser.objects.filter(username=username.lower()).exists():
            raise CommandError("This username already exists.")
        if ShopUser.objects.filter(contact_email=email).exists():
            raise CommandError("This contact email already exists.")
        if ShopUser.objects.filter(contact_phone=phone).exists():
            raise CommandError("This contact phone already exists.")

        manager = ShopUser.objects.create_user(
            username=username,
            password=password,
            name=name,
            contact_email=email,
            contact_phone=phone,
            role=ShopUser.Role.MANAGER,
            status=ShopUser.Status.ACTIVE,
            must_change_password=True,
            is_staff=True,
        )

        self.stdout.write(self.style.SUCCESS("Manager account created successfully."))
        self.stdout.write(f"id: {manager.id}")
        self.stdout.write(f"username: {manager.username}")
        self.stdout.write(f"email: {manager.contact_email}")
        self.stdout.write(f"phone: {manager.contact_phone}")
