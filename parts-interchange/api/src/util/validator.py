

class ValidationRule:
    validation: str
    comparitor: any
    validator: callable
    case_sensitive: bool

    def __init__(self, validation: str, comparitor: any, return_false_on_exception: bool = False, case_sensitive: bool = False):
        self.validator = self.build_validator(validation, comparitor, return_false_on_exception, case_sensitive)
        self.validation = validation
        self.comparitor = comparitor
        self.case_sensitive = case_sensitive

    def build_validator(self, validation: str, comparitor: any, return_false_on_exception: bool, case_sensitive: bool):
        if validation == Validation.MINLEN:
            if not isinstance(comparitor, int):
                raise ValidationRuleException(f'MinLength comparitor value must be an integer. Comparitor: {comparitor}')
            def min_len_val(value) -> bool:
                try:
                    val = len(value) >= comparitor
                except Exception as ex:
                    if return_false_on_exception:
                        return False
                    else:
                        raise ex
                return val
            return min_len_val
        if validation == Validation.MAXLEN:
            if not isinstance(comparitor, int):
                raise ValidationRuleException(f'MaxLength comparitor value must be an integer. Comparitor: {comparitor}')
            def max_len_val(value) -> bool:
                try:
                    val = len(value) <= comparitor
                except Exception as ex:
                    if return_false_on_exception:
                        return False
                    else:
                        raise ex
                return val
            return max_len_val
        if validation == Validation.TYPE:
            if not isinstance(comparitor, type):
                raise ValidationRuleException(f'Type comparitor value must be a type. Comparitor: {comparitor}')
            def type_val(value) -> bool:
                try:
                    val = isinstance(value, comparitor)
                except Exception as ex:
                    if return_false_on_exception:
                        return False
                    else:
                        raise ex
                return val
            return type_val
        if validation == Validation.MIN:
            if not isinstance(comparitor, (int, float)):
                raise ValidationRuleException(f'Min comparitor value must be an int/float. Comparitor: {comparitor}')
            def min_val(value) -> bool:
                try:
                    val = value >= comparitor
                except Exception as ex:
                    if return_false_on_exception:
                        return False
                    else:
                        raise ex
                return val
            return min_val
        if validation == Validation.MAX:
            if not isinstance(comparitor, (int,type)):
                raise ValidationRuleException(f'Max comparitor value must be an int/float. Comparitor: {comparitor}')
            def max_val(value) -> bool:
                try:
                    val = value <= comparitor
                except Exception as ex:
                    if return_false_on_exception:
                        return False
                    else:
                        raise ex
                return val
            return max_val
        if validation == Validation.OPTION_LIST:
            if not isinstance(comparitor, list):
                raise ValidationRuleException(f'Option List comparitor value must be a list. Comparitor: {comparitor}')
            def val_in_options(value) -> bool:
                try:
                    if case_sensitive:
                        return value in comparitor
                    else:
                        return value.lower() in [x.lower() for x in comparitor]
                except Exception as ex:
                    if return_false_on_exception:
                        return False
                    else:
                        raise ex
            return val_in_options
        if validation == Validation.LITERAL:
            def lit_val(value) -> bool:
                try:
                    return value == comparitor
                except Exception as ex:
                    if return_false_on_exception:
                        return False
                    else:
                        raise ex
            return lit_val

class Validation:
    MINLEN = 'minLen'
    MAXLEN = 'maxLen'
    TYPE = 'type'
    MIN = 'min'
    MAX = 'max'
    OPTION_LIST = 'option_list'
    LITERAL = 'literal'

class ValidationException(Exception):
    pass

class ValidationRuleException(Exception):
    pass

class ValidationEntryException(Exception):
    pass

class ValidationEntry:
    path: str
    required: bool
    rule: ValidationRule

    def __init__(self, path: str, rule: ValidationRule, required: bool = False):
        self.path = path
        self.required = required
        self.rule = rule if isinstance(rule, ValidationRule) else None
        if not self.rule:
            raise ValidationEntryException(f'Invalid validation rule passed to constructor, example syntax: ValidationRule(Validation.MIN, 0)')

class Validator:

    def __init__(self, entries: list[ValidationEntry]):
        self.entries = entries
    
    def check(self, input: dict):
        failures = []

        for entry in self.entries:
            val = self.get_val(entry.path, input)
            if not val and entry.required:
                message = f'Expected value at payload.{entry.path} but it was not found'
                if message not in failures:
                    failures.append(message)
            if not val:
                continue
            if not entry.rule.validator(val):
                message = f'Validation rule violated at payload.{entry.path}, validation is {entry.rule.validation}: {entry.rule.comparitor}'
                if message not in failures:
                    failures.append(message)
        
        return {
            'pass': len(failures) == 0,
            'failures': failures
        }
            

    def get_val(self, path, input):
        try:
            keys = path.split('.')
            output = input
            for key in keys:
                output = output[key]
            return output

        except Exception as ex:
            return None
