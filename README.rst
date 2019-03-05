===========
microwallet
===========

.. image:: https://img.shields.io/pypi/v/microwallet.svg
        :target: https://pypi.python.org/pypi/microwallet

.. image:: https://img.shields.io/travis/matejcik/microwallet.svg
        :target: https://travis-ci.org/matejcik/microwallet

.. image:: https://readthedocs.org/projects/microwallet/badge/?version=latest
        :target: https://microwallet.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status

.. image:: https://pyup.io/repos/github/matejcik/microwallet/shield.svg
     :target: https://pyup.io/repos/github/matejcik/microwallet/
     :alt: Updates


Stateless Bitcoin CLI wallet backed by Trezor_ hardware and Blockbook_ indexing servers.
Just plug in your Trezor and go!

You can use microwallet as a highly scriptable CLI, or you can use it as a library
in your Python application.

.. _Trezor: https://trezor.io
.. _Blockbook: https://github.com/trezor/blockbook


Usage
-----

Microwallet is built with Click_ library, which means that it has very nice help screens.
You can view them any time using the ``--help`` argument:

.. code-block:: console

    $ microwallet --help            # show general help
    $ microwallet receive --help    # show help for the 'receive' command

View your Bitcoin balance on your primary account:

.. code-block:: console

    $ microwallet show
    Balance: 0.0001 BTC

Get a fresh receiving address for second Dogecoin account, and confirm the address
on a Trezor screen:

.. code-block:: console

    $ microwallet -c Dogecoin -a 1 receive -s
    DKHVXpTX5y31RF48NkpCF3bs43o83UwMUM
    Please confirm action on your Trezor device

Send 92 million DOGE (9200000000000000 satoshi) to an address:

.. code-block:: console

    $ microwallet -c Dogecoin send DogecoinRecipientAddress 9200000000000000



.. _Click: https://click.palletsprojects.com


Offline signing
---------------

*This is a work in progress.*

With microwallet and trezorctl_, you can prepare a transaction for signing on an online
computer, and sign it with Trezor connected to an offline computer.

1.  On the offline computer, get your XPUB:

    .. code-block:: console

        $ trezorctl get-public-node -n m/49h/0h/0h
        node.depth: 3
        node.fingerprint: b9b82be7
        node.child_num: 2147483648
        node.chain_code: 2bb4(...)
        node.public_key: 02b9(...)
        xpub: xpub6D1weXBcFAo8C(...)

2.  On the online computer, use microwallet to create a transaction sending 10000 satoshi:

    .. code-block:: console

        $ microwallet \
            -x xpub6D1weXBcFAo8C(...) \
            fund 1BitcoinRecipientAddress 10000 \
            -j offline-tx.json

3.  Edit the generated JSON file. Change every ``address_n`` field by prepending
    the path you used with ``get-public-node``.

    *(obviously, this step won't be necessary in future versions)*

    You also have to add **2147483648** (0x80000000) to the numbers.
    I.e., if your path was ``m/49h/0h/0h``, modify the JSON data that says:

    .. code-block:: json

        "address_n": [
            0,
            3
        ],

    to this:

    .. code-block:: json

        "address_n": [
            2147483697,
            2147483648,
            2147483648,
            0,
            3
        ],

    where ``2147483697`` corresponds to "49h" and each ``2147483648`` corresponds to "0h".


Support for `BIP-174 PSBT`_ is being developed.


.. _trezorctl: https://github.com/trezor/python-trezor
.. _`BIP-174 PSBT`: https://github.com/bitcoin/bips/blob/master/bip-0174.mediawiki


Installing
----------

Refer to the `installation guide`_.

.. _`installation guide`: docs/installation.rst


Footer
------

* Free software: GNU General Public License v3
* Documentation: https://microwallet.readthedocs.io.
* This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_
project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
