# -*- coding: UTF-8
# node
#   ****
#
# Implementation of classes handling the HTTP request to /node, public
# exposed API.
import os

from twisted.internet.defer import inlineCallbacks, returnValue
from storm.expr import And

from globaleaks import models, LANGUAGES_SUPPORTED
from globaleaks.models import ConfigL10N, l10n, config
from globaleaks.models.groups import SafeSets
from globaleaks.models.config import NodeFactory
from globaleaks.handlers.base import BaseHandler
from globaleaks.handlers.admin.files import db_get_file
from globaleaks.orm import transact_ro
from globaleaks.rest.apicache import GLApiCache
from globaleaks.settings import GLSettings
from globaleaks.utils.structures import Rosetta, get_localized_values
from globaleaks.utils.sets import disjoint_union


@transact_ro
def serialize_ahmia(store, language):
    """
    Serialize Ahmia.fi descriptor.
    """
    ret_dict = NodeFactory(store).public_export()

    return {
        'title': ret_dict['name'],
        'description': ConfigL10N.get_one(store, language, 'node', 'description').value,
        'keywords': '%s (GlobaLeaks instance)' % ret_dict['name'],
        'relation': ret_dict['public_site'],
        'language': ret_dict['default_language'],
        'contactInformation': u'',
        'type': 'GlobaLeaks'
    }


def db_serialize_node(store, language):
    """
    Serialize node info.
    """
    # Contexts and Receivers relationship
    configured = store.find(models.ReceiverContext).count() > 0

    ro_node = NodeFactory(store).public_export()

    if GLSettings.devel_mode:
        ro_node['submission_minimum_delay'] = 0

    misc_dict = {
        'languages_enabled': l10n.EnabledLanguage.get_all_strs(store),
        'languages_supported': LANGUAGES_SUPPORTED,
        'configured': configured,
        'accept_submissions': GLSettings.accept_submissions,
        'logo': db_get_file(store, u'logo'),
        'css': db_get_file(store, u'css'),
        'homepage': db_get_file(store, u'homepage'),
        'script': db_get_file(store, u'script')
    }

    l10n_dict = l10n.Node_L10N(store).build_localized_dict(language)
    
    return disjoint_union(ro_node, l10n_dict, misc_dict)


@transact_ro
def serialize_node(store, language):
    return db_serialize_node(store, language)


def serialize_context(store, context, language):
    """
    Serialize context description

    @param context: a valid Storm object
    @return: a dict describing the contexts available for submission,
        (e.g. checks if almost one receiver is associated)
    """
    ret_dict = {
        'id': context.id,
        'presentation_order': context.presentation_order,
        'tip_timetolive': context.tip_timetolive,
        'select_all_receivers': context.select_all_receivers,
        'maximum_selectable_receivers': context.maximum_selectable_receivers,
        'show_context': context.show_context,
        'show_recipients_details': context.show_recipients_details,
        'allow_recipients_selection': context.allow_recipients_selection,
        'show_small_receiver_cards': context.show_small_receiver_cards,
        'enable_comments': context.enable_comments,
        'enable_messages': context.enable_messages,
        'enable_two_way_comments': context.enable_two_way_comments,
        'enable_two_way_messages': context.enable_two_way_messages,
        'enable_attachments': context.enable_attachments,
        'show_receivers_in_alphabetical_order': context.show_receivers_in_alphabetical_order,
        'questionnaire': serialize_questionnaire(store, context.questionnaire, language), 
        'receivers': [r.id for r in context.receivers],
        'picture': context.picture.data if context.picture is not None else ''
    }

    return get_localized_values(ret_dict, context, context.localized_keys, language)


def serialize_questionnaire(store, questionnaire, language):
    """
    Serialize the specified questionnaire

    :param store: the store on which perform queries.
    :param language: the language in which to localize data.
    :return: a dictionary representing the serialization of the questionnaire.
    """
    ret_dict = {
        'id': questionnaire.id,
        'key': questionnaire.key,
        'editable': questionnaire.editable,
        'name': questionnaire.name,
        'show_steps_navigation_bar': questionnaire.show_steps_navigation_bar,
        'steps_navigation_requires_completion': questionnaire.steps_navigation_requires_completion,
        'steps': [serialize_step(store, s, language) for s in questionnaire.steps]
    }

    return get_localized_values(ret_dict, questionnaire, questionnaire.localized_keys, language)


def serialize_field_option(option, language):
    """
    Serialize a field option, localizing its content depending on the language.

    :param option: the field option object to be serialized
    :param language: the language in which to localize data
    :return: a serialization of the object
    """
    ret_dict = {
        'id': option.id,
        'presentation_order': option.presentation_order,
        'score_points': option.score_points,
        'trigger_field': option.trigger_field if option.trigger_field else '',
        'trigger_step': option.trigger_step if option.trigger_step else ''
    }

    return get_localized_values(ret_dict, option, option.localized_keys, language)


def serialize_field_attr(attr, language):
    """
    Serialize a field attribute, localizing its content depending on the language.

    :param option: the field attribute object to be serialized
    :param language: the language in which to localize data
    :return: a serialization of the object
    """
    ret_dict = {
        'id': attr.id,
        'name': attr.name,
        'type': attr.type,
        'value': attr.value
    }

    if attr.type == 'bool':
        ret_dict['value'] = True if ret_dict['value'] == 'True' else False
    elif attr.type == u'localized':
        get_localized_values(ret_dict, ret_dict, ['value'], language)

    return ret_dict


def serialize_field(store, field, language):
    """
    Serialize a field, localizing its content depending on the language.

    :param field: the field object to be serialized
    :param language: the language in which to localize data
    :return: a serialization of the object
    """
    # naif likes if we add reference links
    # this code is inspired by:
    #  - https://www.youtube.com/watch?v=KtNsUgKgj9g

    if field.template:
        f_to_serialize = field.template
    else:
        f_to_serialize = field

    attrs = {}
    for attr in store.find(models.FieldAttr, models.FieldAttr.field_id == f_to_serialize.id):
        attrs[attr.name] = serialize_field_attr(attr, language)

    triggered_by_options = [{
        'field': trigger.field_id,
        'option': trigger.id
    } for trigger in field.triggered_by_options]

    ret_dict = {
        'id': field.id,
        'key': f_to_serialize.key,
        'instance': field.instance,
        'editable': field.editable,
        'type': f_to_serialize.type,
        'template_id': field.template_id if field.template_id else '',
        'step_id': field.step_id if field.step_id else '',
        'fieldgroup_id': field.fieldgroup_id if field.fieldgroup_id else '',
        'multi_entry': field.multi_entry,
        'required': field.required,
        'preview': field.preview,
        'stats_enabled': field.stats_enabled,
        'attrs': attrs,
        'x': field.x,
        'y': field.y,
        'width': field.width,
        'triggered_by_score': field.triggered_by_score,
        'triggered_by_options': triggered_by_options,
        'options': [serialize_field_option(o, language) for o in f_to_serialize.options],
        'children': [serialize_field(store, f, language) for f in f_to_serialize.children]
    }

    return get_localized_values(ret_dict, f_to_serialize, field.localized_keys, language)


def serialize_step(store, step, language):
    """
    Serialize a step, localizing its content depending on the language.

    :param step: the step to be serialized.
    :param language: the language in which to localize data
    :return: a serialization of the object
    """
    triggered_by_options = [{
        'field': trigger.field_id,
        'option': trigger.id
    } for trigger in step.triggered_by_options]

    ret_dict = {
        'id': step.id,
        'questionnaire_id': step.questionnaire_id,
        'presentation_order': step.presentation_order,
        'triggered_by_score': step.triggered_by_score,
        'triggered_by_options': triggered_by_options,
        'children': [serialize_field(store, f, language) for f in step.children]
    }

    return get_localized_values(ret_dict, step, step.localized_keys, language)


def serialize_receiver(receiver, language):
    """
    Serialize a receiver description

    :param receiver: the receiver to be serialized
    :param language: the language in which to localize data
    :return: a serializtion of the object
    """
    ret_dict = {
        'id': receiver.user.id,
        'name': receiver.user.public_name,
        'username': receiver.user.username if GLSettings.memory_copy.simplified_login else '',
        'state': receiver.user.state,
        'configuration': receiver.configuration,
        'presentation_order': receiver.presentation_order,
        'contexts': [c.id for c in receiver.contexts],
        'picture': receiver.user.picture.data if receiver.user.picture is not None else ''
    }

    # description and eventually other localized strings should be taken from user model
    get_localized_values(ret_dict, receiver.user, ['description'], language)

    return get_localized_values(ret_dict, receiver, receiver.localized_keys, language)


def db_get_public_context_list(store, language):
    context_list = []

    for context in store.find(models.Context):
        if context.receivers.count():
            context_list.append(serialize_context(store, context, language))

    return context_list


@transact_ro
def get_public_context_list(store, language):
    return db_get_public_context_list(store, language)


def db_get_public_receiver_list(store, language):
    receiver_list = []

    for receiver in store.find(models.Receiver):
        if receiver.user.state == u'disabled':
            continue

        receiver_desc = serialize_receiver(receiver, language)
        # receiver not yet ready for submission return None
        if receiver_desc:
            receiver_list.append(receiver_desc)

    return receiver_list


@transact_ro
def get_public_receiver_list(store, language):
    return db_get_public_receiver_list(store, language)


class PublicResource(BaseHandler):
    @BaseHandler.transport_security_check("unauth")
    @BaseHandler.unauthenticated
    @inlineCallbacks
    def get(self):
        """
        Get all the public resources.
        """
        @transact_ro
        def _get_public_resources(store, language):
            returnValue({
              'node': db_serialize_node(store, language),
              'contexts': db_get_public_context_list(store, language),
              'receivers': db_get_public_receiver_list(store, language)
            })

        ret = yield GLApiCache.get('public', self.request.language,
                                   _get_public_resources, self.request.language)
        self.write(ret)


class AhmiaDescriptionHandler(BaseHandler):
    def _empt_gen(self):
        return None

    @BaseHandler.transport_security_check("unauth")
    @BaseHandler.unauthenticated
    @inlineCallbacks
    def get(self):
        """
        Get the ahmia.fi descriptor
        """
        if GLSettings.memory_copy.ahmia:
            ret = yield GLApiCache.get('ahmia', self.request.language,
                                       serialize_ahmia, self.request.language)

            self.write(ret)
        else:  # in case of disabled option we return 404
            yield self._empt_gen() # TODO remove inlineCallbacks from outer get.
            self.set_status(404)


class RobotstxtHandler(BaseHandler):

    @BaseHandler.transport_security_check("unauth")
    @BaseHandler.unauthenticated
    def get(self):
        """
        Get the robots.txt
        """
        self.set_header('Content-Type', 'text/plain')

        self.write("User-agent: *\n")
        self.write("Allow: /" if GLSettings.memory_copy.allow_indexing else "Disallow: /")
